"""滚动长截图：模拟滚轮并逐帧拼接。"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QGuiApplication, QImage

MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120


def _user32():
    u = ctypes.WinDLL("user32", use_last_error=True)
    u.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    u.SetCursorPos.restype = wintypes.BOOL
    u.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    u.mouse_event.restype = None
    return u


def _cursor_pos() -> QPoint | None:
    pt = wintypes.POINT()
    if not ctypes.windll.user32.GetCursorPos(ctypes.byref(pt)):
        return None
    return QPoint(pt.x, pt.y)


def _grab(rect: QRect) -> QImage:
    """抓取逻辑矩形，返回物理分辨率图像。"""
    screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
    dpr = float(screen.devicePixelRatio()) or 1.0
    pm = screen.grabWindow(0)
    if pm.isNull():
        return QImage()
    img = pm.toImage()
    sg = screen.geometry()
    x = int(round((rect.x() - sg.x()) * dpr))
    y = int(round((rect.y() - sg.y()) * dpr))
    w = max(1, int(round(rect.width() * dpr)))
    h = max(1, int(round(rect.height() * dpr)))
    return img.copy(x, y, w, h)


def _gray_rows(img: QImage) -> tuple[list[memoryview], int, int, QImage]:
    """转灰度，保留原始像素宽度以便区分文字细节。

    返回的 rows 是 memoryview 视图，直接指向灰度图缓冲区（不整帧复制），
    因此必须把 gray 一并返回，保证视图有效。
    """
    gray = img.convertToFormat(QImage.Format_Grayscale8)
    sw, sh = gray.width(), gray.height()
    if sw <= 0 or sh <= 0:
        return [], 0, 0, gray
    line = gray.bytesPerLine()
    buf = gray.constBits()
    if not isinstance(buf, memoryview):
        buf = memoryview(bytes(buf))
    data = memoryview(buf).cast("B")[: line * sh]
    rows = [data[y * line : y * line + sw] for y in range(sh)]
    return rows, sw, sh, gray


def _texture(rows: list[bytes], i: int, w: int) -> int:
    """第 i 行相对上一行的变化量，用来挑“有内容”的条带。"""
    if i <= 0:
        return 0
    a, b = rows[i], rows[i - 1]
    s = 0
    for k in range(0, w, max(3, w // 160)):
        d = a[k] - b[k]
        s += d if d >= 0 else -d
    return s


def _match_offset(prev: QImage, cur: QImage, hint: int | None = None) -> int:
    """返回平滑滚动后新内容相对上一帧的位移（像素）。

    做法：从上一帧挑一段纹理最丰富的条带作为模板，在本帧中搜索其位置。
    找不到可信重叠时返回 -1。
    """
    p_rows, pw, ph, _p_gray = _gray_rows(prev)
    c_rows, cw, ch, _c_gray = _gray_rows(cur)
    if pw == 0 or pw != cw or ph < 24 or ch < 24:
        return -1

    band = max(20, min(ph // 3, 120))
    tex = [0] * ph
    for i in range(1, ph):
        tex[i] = _texture(p_rows, i, pw)

    # 只用下半部分作模板：向下滚动后它仍留在新画面里，可检测的位移更大
    starts = list(range(ph // 2, ph - band + 1, max(1, band // 6)))
    if not starts:
        starts = [max(0, ph - band)]
    best_start, best_tex = -1, 0
    for start in starts:
        t = sum(tex[start : start + band])
        if t > best_tex:
            best_tex, best_start = t, start
    if best_start < 0 or best_tex <= 0:
        return -1

    max_y = ch - band
    if max_y < 1:
        return -1

    def score(y: int, row_step: int, col_step: int) -> float:
        total = 0
        n = 0
        for r in range(best_start, best_start + band, row_step):
            a = p_rows[r]
            b = c_rows[y + (r - best_start)]
            s = 0
            for k in range(0, pw, col_step):
                d = a[k] - b[k]
                s += d if d >= 0 else -d
            total += s
            n += (pw + col_step - 1) // col_step
        return total / max(1, n)

    def refine(cands: list[int], radius: int) -> list[int]:
        out: list[int] = []
        seen: set[int] = set()
        for y in cands:
            for dy in range(-radius, radius + 1):
                yy = y + dy
                if 0 <= yy <= max_y and yy not in seen:
                    seen.add(yy)
                    out.append(yy)
        return out

    # 由粗到细搜索；同分候选全部保留，交给最后的整段复核裁决
    if hint is not None and hint > 0:
        # 连续帧滚动量基本一致：在上一帧位移附近做局部精搜，避免周期内容误配
        lo = max(1, int(hint * 0.6))
        hi = min(ph - 8, int(hint * 1.45) + 2)
        cand = list(range(hi, lo - 1, -1))
        step1 = max(1, band // 6)
        cs1 = max(1, pw // 40)
        scored1 = sorted(
            (score(best_start - s, step1, cs1), best_start - s) for s in cand
        )
        best1 = scored1[0][0] if scored1 else 1e18
        level = [y for s, y in scored1 if s <= best1 + 1e-6][:30]
        step2 = max(1, band // 12)
        cs2 = max(1, pw // 160)
        scored2 = sorted((score(y, step2, cs2), y) for y in refine(level, 1))
        best2 = scored2[0][0] if scored2 else 1e18
        level = [y for s, y in scored2 if s <= best2 + 1e-6][:30]
    else:
        step1 = max(1, band // 6)
        cs1 = max(1, pw // 24)
        scored1 = sorted((score(y, step1, cs1), y) for y in range(0, max_y + 1, 2))
        best1 = scored1[0][0] if scored1 else 1e18
        level = [y for s, y in scored1 if s <= best1 + 1e-6][:40]

        step2 = max(1, band // 12)
        cs2 = max(1, pw // 160)
        level = refine(level, 2)
        scored2 = sorted((score(y, step2, cs2), y) for y in level)
        best2 = scored2[0][0] if scored2 else 1e18
        level = [y for s, y in scored2 if s <= best2 + 1e-6][:60]

    fine_rows = list(range(best_start, best_start + band, 2))
    fine_cols = list(range(0, pw, max(1, pw // 640)))

    def fine(yy: int) -> float:
        total = 0
        for r in fine_rows:
            a = p_rows[r]
            b = c_rows[yy + (r - best_start)]
            t = 0
            for k in fine_cols:
                d = a[k] - b[k]
                t += d if d >= 0 else -d
            total += t
        return total / max(1, len(fine_rows) * len(fine_cols))

    level = refine(level, 1)

    def verify(shift: int, dense: bool = False) -> float | None:
        """整段重叠区域的平均像素差，越小越可信。"""
        overlap = ph - shift
        if overlap < 8:
            return None
        col_div = 400 if dense else 220
        row_cap = 240 if dense else 90
        cols = list(range(0, pw, max(1, pw // col_div)))
        total = 0
        cnt = 0
        for r in range(0, overlap, max(1, overlap // row_cap)):
            a = p_rows[shift + r]
            b = c_rows[r]
            for k in cols:
                total += abs(a[k] - b[k])
            cnt += 1
        return total / max(1, cnt * len(cols))

    # 画面完全没动（已滚到底）时直接判定结束
    still = verify(0)
    if still is not None and still < 0.6:
        return -1

    coarse: list[tuple[float, int]] = []
    for y in level:
        shift = best_start - y
        if shift <= 0 or shift >= ph:
            continue
        v = verify(shift)
        if v is not None:
            coarse.append((v, shift))
    if not coarse:
        return -1
    coarse.sort()
    best_verify = coarse[0][0]
    pool = [s for v, s in coarse[:8] if v <= best_verify + 0.2]
    if not pool:
        pool = [coarse[0][1]]

    dense: list[tuple[float, int]] = []
    for shift in pool[:6]:
        v = verify(shift, dense=True)
        if v is not None:
            dense.append((v, shift))
    if not dense:
        return -1
    best_dense = min(v for v, _s in dense)

    def rank(item: tuple[float, int]) -> float:
        v, s = item
        return v + abs(s - hint) * 0.006 if hint is not None else v

    best_shift = min(dense, key=rank)[1]
    if best_dense > 0.8:
        return -1
    return best_shift


def capture_scrolling(
    rect: QRect,
    max_frames: int = 30,
    wheel_notches: int | None = None,
    on_frame=None,
    should_stop=None,
) -> tuple[QImage, str]:
    """滚动截取 rect 区域。

    on_frame(index, height) 用于进度反馈；should_stop() 返回 True 时中止。
    返回 (拼接图, 状态说明)。
    """
    if rect.width() < 8 or rect.height() < 8:
        return QImage(), "选区太小"

    if wheel_notches is None:
        # 单帧滚动量控制在选区高度的 40% 以内，保证相邻帧有足够重叠
        wheel_notches = max(1, min(6, int(rect.height() * 0.4 / 60)))

    u = _user32()
    center = rect.center()
    u.SetCursorPos(int(center.x()), int(center.y()))
    time.sleep(0.12)
    cur_pos = _cursor_pos()
    if cur_pos is None:
        return QImage(), "无法读取鼠标位置"
    if not rect.adjusted(-40, -40, 40, 40).contains(cur_pos):
        return QImage(), "无法把鼠标移到选区内，请检查权限后重试"

    frames: list[QImage] = []
    first = _grab(rect)
    if first.isNull():
        return QImage(), "抓屏失败"
    frames.append(first)
    last = first

    mode = "wheel"
    failures = 0
    hint: int | None = None
    for i in range(1, max_frames):
        if should_stop and should_stop():
            break
        if mode == "wheel":
            u.mouse_event(
                MOUSEEVENTF_WHEEL, 0, 0, -WHEEL_DELTA * wheel_notches, None
            )
        else:
            _drag_up(rect)
        time.sleep(0.45 if mode == "wheel" else 0.7)

        cur = _grab(rect)
        if cur.isNull():
            break
        off = _match_offset(last, cur, hint)
        if off < 0:
            failures += 1
            if failures == 2:
                time.sleep(0.35)
                cur = _grab(rect)
                off = _match_offset(last, cur, hint)
            if off < 0:
                if mode == "wheel" and failures >= 2:
                    mode = "drag"
                    failures = 0
                    continue
                break
        if off >= cur.height() - 4:
            break  # 与上一帧完全无重叠
        start = cur.height() - off
        appended = cur.copy(0, start, cur.width(), cur.height() - start)
        frames.append(appended)
        last = cur
        hint = off
        failures = 0
        if on_frame:
            on_frame(i, sum(f.height() for f in frames))
        if sum(f.height() for f in frames) > 24000:
            break

    if len(frames) <= 1:
        return QImage(), "内容没有滚动（可能是静态页面）"

    total_h = sum(f.height() for f in frames)
    out = QImage(frames[0].width(), total_h, QImage.Format_ARGB32)
    out.fill(Qt.white)
    y = 0
    p = QPainter(out)
    for f in frames:
        p.drawImage(QPoint(0, y), f)
        y += f.height()
    p.end()
    n = len(frames)
    frames.clear()  # 立刻丢掉分帧，峰值内存只留成品图
    return out, f"已拼接 {n} 帧"


def _drag_up(rect: QRect) -> None:
    """滚轮无效时改用拖拽（部分应用如某些 Electron 页面）。"""
    u = _user32()
    x = rect.center().x()
    u.SetCursorPos(x, rect.bottom() - 30)
    u.mouse_event(0x0002, 0, 0, 0, None)  # LEFTDOWN
    steps = 6
    step = max(6, (rect.height() - 80) // steps)
    for i in range(1, steps + 1):
        u.SetCursorPos(x, rect.bottom() - 30 - step * i)
        time.sleep(0.012)
    u.mouse_event(0x0004, 0, 0, 0, None)  # LEFTUP
