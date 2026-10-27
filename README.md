# Jietu Pro · 截图工具

Windows 桌面截图 + 标注工具，PySide6 实现。常驻托盘，全局快捷键唤起，支持多屏与高 DPI。

## 快速开始

### 方式一：直接运行 exe（推荐，目标机器无需 Python）

双击 `dist\JietuPro.exe` 即可。单文件约 120MB（内置离线 OCR 模型），不依赖 Python 环境，
可直接拷贝到任意 Windows 10/11 机器使用。

### 方式二：源码运行

```bat
setup.bat     :: 首次运行：创建 .venv 并安装依赖
run.bat       :: 启动（常驻托盘）
```

启动后托盘出现蓝色截图图标，按 **Ctrl + Shift + A** 开始框选截图。

## 功能

### 截图方式
| 方式 | 说明 |
| --- | --- |
| 框选截图 | 拖拽任意区域，支持移动 / 八向缩放 / 方向键微调 |
| 全屏截图 | 一次抓取整个虚拟桌面（多屏自动拼接） |
| 窗口截图 | 自动识别鼠标下的窗口并高亮，单击即截（框选界面里单击高亮窗口同样生效） |
| 延迟截图 | 3 / 5 / 10 秒倒计时，方便截菜单、弹窗 |
| 托盘单击 | 直接进入框选模式 |

### 框选时的辅助
- 实时尺寸角标（`宽 × 高`）
- 像素级放大镜：显示坐标与 HEX 颜色，可直接取色
- 窗口智能高亮 + 窗口标题
- 十字辅助线、四角加粗标记、8 个缩放手柄
- 双击直接全屏、`Esc` 退出

### 标注工具
矩形、椭圆、箭头、直线、自由画笔、荧光高亮、马赛克、文字、序号徽章、选择。
支持 10 种预设颜色 + 自定义取色、4 档粗细、撤销 / 重做。

进入编辑时默认是**指针**（选择）状态，与主流截图工具一致：
- 拖动选区内部 = 移动整个选区；拖动四角 / 四边手柄 = 缩放选区
- 点击选区**外**的遮罩区域 = 重新框选
- 单击图元选中（虚线框 + 四角手柄），拖动移动，`Delete` 删除，
  `Ctrl+D` 复制一份，`Ctrl+A` 选中最新图元；选中后改颜色 / 粗细即套用到该图元
- 需要画标注时再点工具条上的工具（或按 `R E A L P H M T N`）
- **文字工具**：支持多行。`Enter` 提交，`Shift+Enter` 换行，`Esc` 放弃

### OCR 文字识别
框选后点工具条「识别文字」（`Ctrl+Shift+O`）：内置 **RapidOCR（PP-OCRv3 模型）**，
完全离线，中文/英文 UI 文字识别准确率高；识别结果可复制或保存为 TXT。

- 模型放在 `vendor/`（numpy / onnxruntime / opencv-headless / rapidocr），随 exe 打包
- **识别在独立助手进程里跑**：主程序常驻内存 ~50MB 不受影响，助手空闲 60 秒自动退出
  - 截图开始时后台预热，点「识别文字」通常 1~2 秒出结果；冷启动约 4~5 秒
- 若 `vendor/` 缺失，自动回退到系统 Windows OCR 引擎（准确率较低）
- 命令行验证打包版识别链路：`JietuPro.exe --ocr 图片.png 结果.txt`
- 调试时可设 `JIETU_OCR_INPROC=1` 让识别在主进程内执行（会驻留 numpy/opencv）

### 滚动长截图
点工具条「滚动长截图」（`Ctrl+Shift+L`）：自动把鼠标移入选区并模拟滚轮，
逐帧拼接成长图，滚到底或按 `Esc` 结束，支持预览后复制 / 保存。

### 图片美化
点工具条「图片美化」（`Ctrl+B`）：加留白、圆角、投影与渐变背景，
实时预览，可复制、另存或直接贴图。

### 历史记录
托盘菜单「历史记录…」：以缩略图浏览最近截图，可复制、贴图、另存、删除。
默认保留 60 张（设置中可改），存放在 `%APPDATA%\JietuPro\history`。

### 输出
- **复制到剪贴板**（Enter / Ctrl+C）
- **保存到文件**（Ctrl+S，PNG / JPG，文件名格式可在设置中自定义）
- **另存为**（Ctrl+Shift+S）
- **贴图到屏幕**（F3）：截图钉在桌面最上层，可拖动、八个方向缩放、
  滚轮缩放、调透明度、圆角阴影边框，右键更多操作

## 快捷键

| 按键 | 作用 |
| --- | --- |
| `Ctrl+Shift+A` | 框选截图（可在设置中修改） |
| `Ctrl+Shift+F` | 全屏截图 |
| `Enter` / `Ctrl+C` | 复制并退出 |
| `Ctrl+S` / `Ctrl+Shift+S` | 保存 / 另存为 |
| `Ctrl+Z` / `Ctrl+Y` | 撤销 / 重做 |
| `Ctrl+Shift+O` | OCR 识别文字 |
| `Ctrl+Shift+L` | 滚动长截图 |
| `Ctrl+B` | 图片美化 |
| `Ctrl+D` / `Ctrl+A` / `Delete` | 复制图元 / 选中最新图元 / 删除选中图元 |
| `F3` | 贴图 |
| `Esc` / 右键 | 取消 |
| `R E A L P H M T N S` | 切换标注工具 |
| `Ctrl+滚轮` | 调整标注粗细 |
| `方向键` / `Shift+方向键` | 移动选区 / 调整选区大小 |

> 若快捷键被其他软件占用，程序会自动切换到备选组合并在托盘提示。

## 设置

托盘右键 → 设置：保存目录、图片格式与质量、文件名格式、遮罩深浅、快捷键、
放大镜与窗口识别开关、历史记录与保留张数、开机自启。

配置文件位置：`%APPDATA%\JietuPro\config.json`

## 目录结构

```
main.py                入口（单实例 + 托盘）
jietu/
  config.py            配置读写
  capture.py           多屏抓取、高 DPI 裁剪、窗口检测（Win32/DWM）
  overlay.py           全屏遮罩、框选、标注编辑、输出
  annotations.py       图元模型与渲染
  toolbar.py           浮动工具条、调色板、粗细面板
  panels.py            OCR 结果窗、Toast、长截图预览
  ocr.py               OCR（RapidOCR 优先，Windows OCR 兜底）
  longshot.py          滚轮长截图与逐帧拼接
  beautify.py          图片美化（留白 / 圆角 / 投影 / 背景）
  history.py           截图历史记录
  pin.py               贴图窗口
  app.py               托盘、菜单、快捷键、截图调度
  hotkey.py            全局热键（RegisterHotKey）
  settings_dialog.py   设置面板
  icons.py             QPainter 矢量图标
tests/
  selftest.py          无头自检
  interaction.py       交互流程测试
  smoke_gui.py         真实抓屏冒烟测试
  visual_check.py      渲染效果截图
vendor/                离线 OCR 依赖与模型（rapidocr / onnxruntime / opencv / numpy）
```

## 打包成 exe

已提供 `JietuPro.spec`，重新打包：

```bat
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean JietuPro.spec
```

打包前需释放目录锁：`Get-Process JietuPro | Stop-Process -Force`。

OCR 依赖已解压到 `vendor/`（不占系统环境），打包时通过 spec 的 `pathex` + `datas`
一并收进 exe；如需升级识别精度，替换 `vendor/rapidocr_onnxruntime/models` 下的模型即可。

产物：`dist\JietuPro.exe`（约 120MB，单文件，免安装，内含离线 OCR 模型）。

spec 中已排除 QtWebEngine / Qt3D / QtMultimedia / QtQuick / QtSql 等未使用模块，
并保留 `qwindows`（平台）、`qjpeg` / `qico`（图片格式）等必需插件。

## 排查问题

程序运行日志位于 `%APPDATA%\JietuPro\`：

| 文件 | 内容 |
| --- | --- |
| `error.log` | 未捕获异常堆栈 |
| `runtime.log` | 无控制台模式下的标准输出/错误 |
| `ipc.log` | 单实例转发、截图触发记录 |
| `config.json` | 全部设置项 |
| `history\` | 截图历史（缩略图 PNG） |

打包版可自检核心能力（抓屏、PNG/JPG 保存、标注渲染、剪贴板），结果写入
`%TEMP%\jietu_exe_check.txt`：

```bat
JietuPro.exe --selftest
```

## 说明

- 仅支持 Windows（依赖 `user32` / `dwmapi` 做窗口检测与全局热键）。
- 抓屏使用 `QScreen.grabWindow`，不依赖额外驱动；多屏与 125%/150% 缩放下输出保持物理像素清晰度。
- exe 为单文件模式，首次启动需解压到临时目录，约 2~4 秒；之后常驻托盘不重复启动。
- 若杀毒软件拦截全局热键或开机自启，请在安全软件中放行。
- 未做代码签名，SmartScreen 可能提示"未知发布者"，点"更多信息 → 仍要运行"即可。
