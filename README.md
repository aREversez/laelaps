# language-tools

双语文件 (docx/xlsx/csv) → 语料库格式 (sdltm/tmx) 转换库，以及语料库格式互转 (tmx↔sdltm)。

架构、阶段规划、已知限制见 [DESIGN.md](./DESIGN.md)。

## 当前状态：Phase 5（桌面 GUI 工具箱，第一个工具）已完成

Phase 0-4（库 + CLI）：见上方 DESIGN.md 链接，`language_tools/` 包，`biconvert` 命令行工具。

Phase 5（新增）：
- `toolbox/` — 原生桌面 GUI（PySide6），壳 + 可插拔工具架构，为以后陆续加更多语言管理工具（术语管理、QA报告等）打基础，不是绑死单一功能的界面
- `toolbox/tools/corpus_convert/` — 第一个工具，直接 `import language_tools.api` 调用同一个 `convert()`，转换在 `QThread` 里跑，不卡界面
- `python -m toolbox.main` 启动；`pip install -e ".[gui]"` 装 GUI 依赖
- `packaging/language-toolbox.spec` — PyInstaller 打包配置，`pyinstaller packaging/language-toolbox.spec` 产出 exe（Windows 上跑这条命令；本项目在 Linux 沙盒里验证过同一份 spec 打包链路本身没问题，但最终 Windows exe 需要在 Windows 上构建）
- GUI 测试用 `QT_QPA_PLATFORM=offscreen` + `pytest-qt`，无头环境下也能跑真实交互测试（含一次端到端的真实转换）

新增工具的步骤见 DESIGN.md 第13节末尾——不需要碰壳代码，新建文件夹 + 注册一个 `ToolSpec` 就行。

## 用法

Python API：

```python
from language_tools import convert

convert("input.docx", "output_basename", src_lang="en-US", tgt_lang="zh-CN")
# 生成 output_basename.sdltm / .tmx / .csv
```

命令行（`pip install -e .` 后可用）：

```bash
biconvert input.docx --src en-US --tgt zh-CN                # 输出 input.sdltm/.tmx/.csv
biconvert input.xlsx -o out.tmx --src en-US --tgt zh-CN      # 只要tmx
biconvert a.tmx --to sdltm                                    # 语料库互转，语言自动推断
biconvert input.docx --src en-US --tgt zh-CN --layout table   # 手动指定docx版式
biconvert input.docx --src en-US --tgt zh-CN --min-confidence 0.6  # 低质量TU不进sdltm/tmx，仍在csv里可查
```

桌面 GUI：

```bash
pip install -e ".[gui]"
python -m toolbox.main
```

## 测试

```bash
pip install -e ".[dev,gui]"
pytest tests/                          # 库 + CLI 测试
QT_QPA_PLATFORM=offscreen pytest tests/  # 含 GUI 测试的完整套件（无显示器环境用这条）
```

## 尚未实现

- 后续工具：术语管理、QA 报告查看器等（陆续加，见 DESIGN.md 第13节的接入步骤）
