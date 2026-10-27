"""OCR：优先使用 RapidOCR（PaddleOCR 模型，离线、中文准确率高），
不可用时回退到 Windows 内置 OCR（Windows.Media.Ocr）。

RapidOCR 依赖放在项目 vendor/ 目录（numpy / onnxruntime / opencv-headless /
rapidocr 模型），打包时一并进 exe。
"""
from __future__ import annotations

import atexit
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from PySide6.QtGui import QImage

_VENDOR = Path(__file__).resolve().parent.parent / "vendor"
if _VENDOR.is_dir() and str(_VENDOR) not in sys.path:
    sys.path.insert(0, str(_VENDOR))

_PS_SCRIPT = r"""
param([string]$Path, [string]$Out)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]
function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) {
    [System.IO.File]::WriteAllText($Out, "ERR:系统未安装 OCR 语言包", [System.Text.Encoding]::UTF8)
    exit 2
}
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$sb = New-Object System.Text.StringBuilder
foreach ($line in $result.Lines) {
    [void]$sb.AppendLine($line.Text)
}
[System.IO.File]::WriteAllText($Out, $sb.ToString(), [System.Text.Encoding]::UTF8)
"""


class OcrResult:
    def __init__(self, ok: bool, text: str = "", error: str = ""):
        self.ok = ok
        self.text = text
        self.error = error

    @property
    def lines(self) -> list[str]:
        return [ln.strip() for ln in self.text.splitlines() if ln.strip()]


_available_cache: bool | None = None
_rapid_engine = None
_rapid_error = ""
_last_used = 0.0  # 上次真正识别的时间
_last_active = 0.0  # 上次预热 / 启动识别助手的时间
_IDLE_RELEASE = 60.0

_CJK_GAP = re.compile(
    r"(?<=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])[ \t]+"
    r"(?=[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef])"
)


def _tidy(text: str) -> str:
    """去掉 BOM 与 OCR 在相邻汉字之间插入的多余空格。"""
    text = text.replace("\ufeff", "").replace("\r\n", "\n")
    lines = [_CJK_GAP.sub("", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


# ------------------------------------------------------------------ RapidOCR
def _rapid_spec_ok() -> bool:
    try:
        return importlib.util.find_spec("rapidocr_onnxruntime") is not None
    except Exception:
        return False


def _get_rapid_engine():
    global _rapid_engine, _rapid_error
    if _rapid_engine is not None:
        return _rapid_engine
    try:
        from rapidocr_onnxruntime import RapidOCR

        _rapid_engine = RapidOCR()
        _rapid_error = ""
    except Exception as ex:  # 模型缺失 / 依赖不完整
        _rapid_error = str(ex)
        _rapid_engine = None
    return _rapid_engine


def _boxes_to_text(res, min_score: float = 0.5) -> str:
    """把检测框按行列排好，拼成多行文本。"""
    items = []
    for row in res or []:
        try:
            box, text, score = row[0], row[1], float(row[2])
        except Exception:
            continue
        if not text or score < min_score:
            continue
        ys = [float(p[1]) for p in box]
        xs = [float(p[0]) for p in box]
        cy = (min(ys) + max(ys)) / 2.0
        h = max(1.0, max(ys) - min(ys))
        items.append((cy, min(xs), h, text))
    if not items:
        return ""
    items.sort(key=lambda t: (t[0], t[1]))
    avg_h = sum(t[2] for t in items) / len(items)
    tol = max(6.0, avg_h * 0.6)

    lines: list[list[tuple[float, str]]] = []
    centers: list[float] = []
    for cy, x, _h, text in items:
        if centers and abs(cy - centers[-1]) <= tol:
            lines[-1].append((x, text))
            n = len(lines[-1])
            centers[-1] = (centers[-1] * (n - 1) + cy) / n
        else:
            lines.append([(x, text)])
            centers.append(cy)

    out = []
    for line in lines:
        line.sort(key=lambda t: t[0])
        out.append(" ".join(t for _x, t in line))
    return "\n".join(out)


def _recognize_rapid(img_path: str) -> OcrResult:
    global _last_used
    engine = _get_rapid_engine()
    if engine is None:
        return OcrResult(False, error=_rapid_error or "RapidOCR 不可用")
    try:
        _last_used = time.time()
        res, _elapse = engine(img_path)
    except Exception as ex:
        return OcrResult(False, error=f"RapidOCR 失败：{ex}")
    text = _tidy(_boxes_to_text(res))
    return OcrResult(True, text=text)


# ------------------------------------------------------------------ WinRT
def _script_path() -> str:
    path = os.path.join(tempfile.gettempdir(), "jietu_ocr.ps1")
    try:
        if not os.path.exists(path) or os.path.getsize(path) < 200:
            with open(path, "w", encoding="utf-8-sig") as f:
                f.write(_PS_SCRIPT)
    except Exception:
        pass
    return path


def _winrt_available() -> bool:
    if sys.platform != "win32":
        return False
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                "[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] "
                "| Out-Null; [Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages.Count",
            ],
            capture_output=True,
            timeout=25,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        txt = out.stdout.decode("utf-8", "replace").strip()
        return out.returncode == 0 and txt.isdigit() and int(txt) > 0
    except Exception:
        return False


def _recognize_winrt(img_path: str) -> OcrResult:
    if sys.platform != "win32":
        return OcrResult(False, error="仅支持 Windows")
    out_path = ""
    try:
        fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="jietu_ocr_out_")
        os.close(fd)
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                _script_path(),
                "-Path",
                img_path,
                "-Out",
                out_path,
            ],
            capture_output=True,
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = ""
        try:
            with open(out_path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except Exception:
            text = ""
        if text.startswith("ERR:"):
            return OcrResult(False, error=text[4:].strip())
        if proc.returncode != 0 and not text:
            err = proc.stderr.decode("utf-8", "replace").strip()
            return OcrResult(False, error=(err or "OCR 调用失败")[:300])
        return OcrResult(True, text=_tidy(text))
    except subprocess.TimeoutExpired:
        return OcrResult(False, error="OCR 超时")
    except Exception as ex:
        return OcrResult(False, error=str(ex))
    finally:
        if out_path:
            try:
                os.remove(out_path)
            except Exception:
                pass


# ------------------------------------------------------------------ 对外接口
def backend() -> str:
    """当前生效的识别引擎：rapid / winrt / none"""
    if _rapid_spec_ok():
        return "rapid"
    if _winrt_available():
        return "winrt"
    return "none"


def engine_ready() -> bool:
    """模型是否已加载（首次识别需要几秒加载模型）。"""
    return _rapid_engine is not None


def release() -> None:
    """释放识别模型占用的内存（约 25MB），下次识别会自动重新加载。"""
    global _rapid_engine
    if _rapid_engine is None:
        return
    _rapid_engine = None
    import gc

    gc.collect()


def idle_seconds() -> float:
    """距离上次识别/预热过去了多少秒。

    从未使用过时返回无穷大：早期版本返回 0，导致空闲释放逻辑永远判定为
    “刚用过”，预热出来的识别助手进程（numpy + onnxruntime，数百 MB）
    一直留在内存里。
    """
    t = max(_last_used, _last_active)
    if t <= 0:
        return float("inf")
    return max(0.0, time.time() - t)


def release_if_idle(idle: float = _IDLE_RELEASE) -> bool:
    """识别后空闲超过 idle 秒则释放模型/结束助手进程，返回是否执行了释放。"""
    global _last_used, _last_active
    if idle_seconds() <= idle:
        return False
    did = False
    if engine_ready():
        release()
        did = True
    if _server_proc is not None and _server_proc.poll() is None:
        shutdown()
        did = True
    if did:
        _last_used = 0.0
        _last_active = 0.0
    return did


def available() -> bool:
    """是否有可用的 OCR 引擎。结果缓存，避免重复探测。"""
    global _available_cache
    if _available_cache is not None:
        return _available_cache
    if _rapid_spec_ok():
        _available_cache = True
    else:
        _available_cache = _winrt_available()
    return bool(_available_cache)


def _helper_cmd(img_path: str, out_path: str) -> list[str]:
    """调用自身 `--ocr` 子命令；重依赖（numpy/opencv/onnxruntime）只在子进程里加载。"""
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ocr", img_path, out_path]
    entry = Path(__file__).resolve().parent.parent / "main.py"
    return [sys.executable, str(entry), "--ocr", img_path, out_path]


def _server_cmd(dir_path: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--ocr-server", dir_path]
    entry = Path(__file__).resolve().parent.parent / "main.py"
    return [sys.executable, str(entry), "--ocr-server", dir_path]


def _recognize_child(img_path: str) -> OcrResult:
    out_path = ""
    try:
        fd, out_path = tempfile.mkstemp(suffix=".txt", prefix="jietu_ocr_out_")
        os.close(fd)
        proc = subprocess.run(
            _helper_cmd(img_path, out_path),
            capture_output=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        text = ""
        try:
            with open(out_path, "r", encoding="utf-8-sig") as f:
                text = f.read()
        except Exception:
            text = ""
        if text.startswith("ERR:"):
            return OcrResult(False, error=text[4:].strip())
        if proc.returncode != 0 and not text:
            err = (proc.stderr or b"").decode("utf-8", "replace").strip()
            return OcrResult(False, error=(err or "识别进程异常退出")[:300])
        return OcrResult(True, text=_tidy(text))
    except subprocess.TimeoutExpired:
        return OcrResult(False, error="识别超时")
    except Exception as ex:
        return OcrResult(False, error=str(ex))
    finally:
        if out_path:
            try:
                os.remove(out_path)
            except Exception:
                pass


# ------------------------------------------------------- 常驻识别助手进程
_SERVER_DIR = Path(tempfile.gettempdir()) / "jietu_ocr_srv"
_server_proc: subprocess.Popen | None = None
_server_lock = threading.Lock()


def _server_start() -> subprocess.Popen | None:
    global _server_proc
    try:
        shutil.rmtree(_SERVER_DIR, ignore_errors=True)
        _SERVER_DIR.mkdir(parents=True, exist_ok=True)
        _server_proc = subprocess.Popen(
            _server_cmd(str(_SERVER_DIR)),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        _server_proc = None
    return _server_proc


def shutdown() -> None:
    """结束常驻识别进程（内存全部归还）。"""
    global _server_proc, _last_active
    with _server_lock:
        proc, _server_proc = _server_proc, None
    _last_active = 0.0
    if proc is None:
        return
    # onefile 打包后 --ocr-server 会再开一个子进程，必须按进程树结束
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
            capture_output=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except Exception:
            pass
    try:
        proc.wait(timeout=5)
    except Exception:
        pass


def warm() -> None:
    """预先启动识别助手，让首次识别不用等模型加载。"""
    global _last_active
    if os.environ.get("JIETU_OCR_INPROC") == "1" or not _rapid_spec_ok():
        return
    _last_active = time.time()
    with _server_lock:
        if _server_proc is None or _server_proc.poll() is not None:
            _server_start()


def _recognize_server(img_path: str) -> OcrResult | None:
    """通过常驻进程识别；失败返回 None（调用方回退到一次性子进程）。"""
    global _server_proc
    with _server_lock:
        if _server_proc is None or _server_proc.poll() is not None:
            _server_start()
        proc = _server_proc
        if proc is None:
            return None
        out_path = _SERVER_DIR / "out.txt"
        req = _SERVER_DIR / "req.txt"
        res = _SERVER_DIR / "res.txt"
        try:
            for p in (out_path, res):
                if p.exists():
                    p.unlink()
            tmp = _SERVER_DIR / "req.tmp"
            tmp.write_text(f"{img_path}\n{out_path}", encoding="utf-8")
            os.replace(tmp, req)
            deadline = time.time() + 120
            while not res.exists():
                if proc.poll() is not None or time.time() > deadline:
                    return None
                time.sleep(0.015)
            status = res.read_text(encoding="utf-8").strip()
            text = out_path.read_text(encoding="utf-8-sig") if out_path.exists() else ""
            if status == "OK":
                return OcrResult(True, text=_tidy(text))
            return OcrResult(False, error=(text[4:].strip() if text.startswith("ERR:") else "识别失败"))
        except Exception:
            return None
        finally:
            try:
                for p in (req, res, _SERVER_DIR / "req.tmp", out_path):
                    if p.exists():
                        p.unlink()
            except Exception:
                pass


def serve(dir_path: str, idle_exit: float = 60.0) -> int:
    """识别助手主循环：由 `--ocr-server <dir>` 调用，空闲 idle_exit 秒后退出。"""
    d = Path(dir_path)
    req = d / "req.txt"
    res = d / "res.txt"
    try:
        _get_rapid_engine()  # 提前加载模型，缩短首次识别
    except Exception:
        pass
    last = time.time()
    try:
        (d / 'ready').write_text('1', encoding='utf-8')
    except Exception:
        pass
    while True:
        if req.exists():
            try:
                lines = req.read_text(encoding="utf-8").splitlines()
                req.unlink(missing_ok=True)
                if len(lines) >= 2:
                    result = recognize_file(lines[0].strip())
                    out = Path(lines[1].strip())
                    out.write_text(
                        result.text if result.ok else f"ERR:{result.error}",
                        encoding="utf-8",
                    )
                    res.write_text("OK" if result.ok else "ERR", encoding="utf-8")
            except Exception:
                pass
            last = time.time()
            continue
        if time.time() - last > idle_exit:
            return 0
        time.sleep(0.02)


atexit.register(shutdown)


def recognize_file(path: str) -> OcrResult:
    """在当前进程内识别图片文件（会把 numpy/opencv/onnxruntime 加载进本进程）。"""
    if _rapid_spec_ok():
        res = _recognize_rapid(path)
        if res.ok:
            return res
        if not _winrt_available():
            return res
    return _recognize_winrt(path)


def recognize(img: QImage) -> OcrResult:
    """识别图片中的文字。同步阻塞，调用方应放到后台线程。

    默认在独立子进程里识别（用完即退，主程序不驻留 numpy/opencv/onnxruntime）。
    设置环境变量 JIETU_OCR_INPROC=1 可在当前进程内识别（调试用）。
    """
    if img.isNull():
        return OcrResult(False, error="空图片")

    global _last_used
    _last_used = time.time()
    img_path = ""
    try:
        fd, img_path = tempfile.mkstemp(suffix=".png", prefix="jietu_ocr_in_")
        os.close(fd)
        if not img.save(img_path, "PNG"):
            return OcrResult(False, error="临时图片保存失败")

        if not _rapid_spec_ok() and not _winrt_available():
            return OcrResult(False, error="系统未安装可用的 OCR 引擎")

        if os.environ.get("JIETU_OCR_INPROC") == "1":
            return recognize_file(img_path)

        res = _recognize_server(img_path)
        if res is not None and res.ok:
            return res
        if res is not None and not _rapid_spec_ok():
            return res

        res = _recognize_child(img_path)
        if res.ok:
            return res
        if _rapid_spec_ok():
            return res
        return _recognize_winrt(img_path)
    except Exception as ex:
        return OcrResult(False, error=str(ex))
    finally:
        if img_path:
            try:
                os.remove(img_path)
            except Exception:
                pass
