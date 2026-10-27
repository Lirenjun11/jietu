# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：单文件 exe，目标机器无需安装 Python。"""

EXCLUDES = [
    # 开发/测试用不到的标准库
    "tkinter", "unittest", "pydoc", "doctest", "test", "lib2to3",
    # 科学计算里用不到的大块头
    "matplotlib", "scipy", "pandas", "IPython", "notebook", "torch",
    "sklearn", "sympy", "pytest", "setuptools", "pip",
    # 本项目用不到的 Qt 重型模块（显著减小体积）
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.QtQmlModels",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtSerialPort",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtSvgWidgets",
]

a = Analysis(
    ["main.py"],
    pathex=[".", "vendor"],
    binaries=[],
    datas=[
        ("assets/app.ico", "assets"),
        # RapidOCR 的模型与配置必须随 exe 一起打包（离线识别）
        ("vendor/rapidocr_onnxruntime", "rapidocr_onnxruntime"),
    ],
    hiddenimports=[
        "PySide6.QtNetwork",
        "rapidocr_onnxruntime",
        "rapidocr_onnxruntime.rapid_ocr_api",
        "rapidocr_onnxruntime.ch_ppocr_v3_det",
        "rapidocr_onnxruntime.ch_ppocr_v3_rec",
        "rapidocr_onnxruntime.ch_ppocr_v2_cls",
        "jietu.ocr",
        "jietu.beautify",
        "jietu.panels",
        "jietu.longshot",
        "jietu.history",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="JietuPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/app.ico",
)
