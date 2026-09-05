# language-tools

语言管理（翻译/本地化）工具箱。第一个工具是**双语语料转换**：把 docx/xlsx/csv/tsv 这类双语文档转换成 Trados 等 CAT 工具能用的翻译记忆库格式（sdltm/tmx），也支持 tmx↔sdltm 互转。提供 Python 库、命令行工具、桌面 GUI 三种使用方式，往后会陆续加入更多语言管理相关的工具（术语管理、QA 报告查看器等）。

## 功能特性

- **双语文档 → 翻译记忆库**：docx（三种版式）、xlsx、csv/tsv → sdltm、tmx、csv
- **语料库互转**：tmx ↔ sdltm，语言自动从内容识别
- 内置 Gale-Church 式句级对齐算法，处理常见缩写（a.m./e.g./U.S. 等）不误切句
- 轻量 QA 检查：空值、长度比异常、重复条目、数字不匹配，可选导出为审阅报告
- 桌面 GUI（PySide6），也可以纯命令行/脚本调用
- 打包成本地 Windows exe，不需要联网、不上传文件

## 安装

```bash
git clone https://github.com/aREversez/language-tools.git
cd language-tools
pip install -e .              # 库 + biconvert 命令行
pip install -e ".[gui]"       # 再加上桌面GUI
```

## 快速开始

### 桌面 GUI

```bash
python -m toolbox.main
```

浏览选择文件 → 双语源文件需要填源/目标语言（语料库文件可留空自动识别）→ 需要的话调整 docx 版式 → 勾选输出格式 → 点转换。

### 命令行

```bash
biconvert input.docx --src en-US --tgt zh-CN                       # 生成 input.sdltm/.tmx/.csv
biconvert input.xlsx -o out.tmx --src en-US --tgt zh-CN            # 只要 tmx
biconvert a.tmx --to sdltm                                          # 语料库互转，语言自动识别
biconvert input.docx --src en-US --tgt zh-CN --layout table         # 手动指定 docx 版式
biconvert input.docx --src en-US --tgt zh-CN --min-confidence 0.6   # 低质量条目不进sdltm/tmx，仍在csv可查
```

`biconvert --help` 看完整参数。

### 作为 Python 库

```python
from language_tools import convert

convert("input.docx", "output_basename", src_lang="en-US", tgt_lang="zh-CN")
# 生成 output_basename.sdltm / .tmx / .csv
```

## 支持的输入文件格式

**这部分决定了你要提供的文档必须长成什么样**，格式不对会转换失败或者对齐出错。

### docx 双语文件（三种版式，自动识别，也可以用 `--layout` / GUI 下拉框手动指定）

**编号版式**（`numbered`）—— 不是逐段交替编号，而是**先列完整块源语段落，再接完整块译语段落**，靠"编号第二次从 1 开始"判断分界：

```
[1] Dr. Smith arrived at 9 a.m.
[2] The train departs at 6 p.m.
[1] 史密斯博士上午9点到达。
[2] 火车下午6点出发。
```

**表格版式**（`table`）—— 左右对齐，2 列表格，第 1 列源语第 2 列译语，一行一对：

| Source | Target |
|---|---|
| Dr. Smith arrived at 9 a.m. | 史密斯博士上午9点到达。 |
| The train departs at 6 p.m. | 火车下午6点出发。 |

首行如果看起来像表头（内容短、没有句末标点）会自动跳过，也可以用 `header=True/False` 强制指定。超过 2 列时默认取最后两列，可用 `src_col_index`/`tgt_col_index` 指定其他列。

**交替段落版式**（`alternating`）—— 一段源语紧接一段目标语，如此交替：

```
Dr. Smith arrived at 9 a.m.
史密斯博士上午9点到达。
The train departs at 6 p.m.
火车下午6点出发。
```

自动识别顺序是表格 → 编号 → 交替（交替排最后，因为它没有正向识别特征，任何偶数段落数的单语文档都"符合"这个形状）。识别错了用 `--layout` 手动指定。

### xlsx / csv / tsv

约定和 docx 表格版式一致：2 列，第一列源语第二列译语，一行一对，首行表头自动探测。列不是恰好 2 列时同样取最后两列，可覆盖——xlsx 用 Excel 字母指定（`--src-col B --tgt-col C`），docx表格/csv 用 0-based 序号指定。csv/tsv 编码按 `utf-8-sig → utf-8 → gb18030` 顺序自动尝试，国内 Excel 导出的非 UTF-8 文件也能读。

### tmx / sdltm（作为输入 = 语料库互转，不是双语源文件）

这两种当输入时走的是不一样的路径：文件内容本身已经是句子级别的翻译单元，直接读取，不会再跑分句/对齐算法。`--src`/`--tgt` 可以不填，会从文件内容自动识别。

## 开发

```bash
pip install -e ".[dev,gui]"
pytest tests/                            # 库 + CLI 测试
QT_QPA_PLATFORM=offscreen pytest tests/  # 含 GUI 测试的完整套件（无显示器环境用这条）
```

打包 Windows exe（需要在 Windows 上执行，PyInstaller 不能跨平台编译）：

```bash
pyinstaller packaging/language-toolbox.spec
```

架构设计、开发阶段规划、已知限制、新增工具的接入方式见 [DESIGN.md](./DESIGN.md)。
