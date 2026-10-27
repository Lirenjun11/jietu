"""配置管理：读写 %APPDATA%/JietuPro/config.json"""
from __future__ import annotations

import json
import os
from pathlib import Path

APP_NAME = "JietuPro"
APP_TITLE = "Jietu Pro 截图"


def app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_save_dir() -> str:
    pics = Path.home() / "Pictures"
    if not pics.exists():
        pics = Path.home()
    return str(pics / "Screenshots")


DEFAULTS: dict = {
    "save_dir": _default_save_dir(),
    "image_format": "png",          # png / jpg
    "jpg_quality": 95,
    "auto_copy": True,              # 保存后自动复制到剪贴板
    "auto_save": False,             # 确认后自动保存（不显示编辑界面时用）
    "show_magnifier": True,         # 选框时显示放大镜
    "show_window_detect": True,     # 悬停高亮窗口
    "overlay_alpha": 0.45,          # 遮罩不透明度 0~0.9
    "border_width": 3,              # 默认标注线宽
    "border_color": "#FF3B30",      # 默认标注颜色
    "hotkey_capture": "ctrl+shift+a",
    "hotkey_fullscreen": "ctrl+shift+f",
    "enable_hotkey": True,
    "play_sound": True,
    "copy_path_after_save": False,
    "remember_tool": True,          # 记住上次使用的工具
    "last_tool": "rect",
    "last_color": "#FF3B30",
    "last_width": 3,
    "pin_always_on_top": True,
    "filename_pattern": "Jietu_{date}_{time}",
    "save_history": True,           # 保存截图历史缩略图
    "history_limit": 60,            # 历史记录最多保留张数
    "ocr_preload": False,           # 截图后预热 OCR 助手（更快，但常驻占内存）
}


class Config:
    def __init__(self) -> None:
        self.path = app_data_dir() / "config.json"
        self.data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    for k, v in raw.items():
                        if k in DEFAULTS:
                            self.data[k] = v
        except Exception:
            pass

    def save(self) -> None:
        try:
            self.path.write_text(
                json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def __getitem__(self, key):
        return self.data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.data[key] = value

    def get(self, key, default=None):
        return self.data.get(key, DEFAULTS.get(key, default))

    def update(self, **kw) -> None:
        self.data.update(kw)
        self.save()


config = Config()
