# bi-corpus-tools 开发方案（v1，供 opencode 实现）

> `bi-corpus-tools` 是这份文档最初的项目代号，下文出现的 `corpustools/`
> 包名、目录结构等也是当时的设计方案，与最终实现不完全一致——核心库最终
> 落地为 `language_tools` 包，仓库先叫 `language-tools`，现已改名为
> `laelaps`（GitHub: `aREversez/laelaps`），详见第 12 节。这里保留原文不
> 改，作为设计思路的历史记录；想看当前实际的目录结构/包名，直接看仓库本身。

## 0. 目标

把 `docx_to_sdltm.py`（单一脚本，docx编号版式→sdltm）演化为一个可复用的 Python 库：

- 支持多种**双语原始文件**：docx（编号版式 / 表格版式）、xlsx、csv/tsv
- 支持多种**语料库格式**互转：tmx ↔ sdltm
- 架构上做到 N 种输入 × M 种输出，而不是写 N×M 个专用转换器

产物形式：先做纯 Python 库（`pip install -e .` 可用），GUI 以后再说。

---

## 1. 核心架构：Reader → Align → Writer（轮辐式）

```
双语原始文件 (docx/xlsx/csv)
        │  BilingualReader.read()
        ▼
  ParagraphPair 列表  ← 段落/整行级别，尚未拆句
        │  aligner.align()  (已有的DP对齐算法)
        ▼
  TranslationUnit 列表  ← 句子级 IR，所有格式的公共交换层
        │                              ▲
        │  CorpusWriter.write()        │  CorpusReader.read()
        ▼                              │
  语料库文件 (sdltm/tmx)  ─────────────┘
```

**关键点**：`TranslationUnit` 是唯一的公共数据结构。原始双语文件进来要过一次对齐算法；语料库文件（tmx/sdltm）本身已经是句子级的，读进来直接就是 `TranslationUnit` 列表，不需要再跑对齐——这也是为什么语料库互转（tmx→sdltm）比双语文件转换（docx→sdltm）简单得多的原因，不要在 Phase 2 的 reader 里误用对齐算法。

---

## 2. 数据模型 (`corpustools/model.py`)

已知会用到的字段（guid、时间戳、来源文件/行号）直接类型化，不要塞进 `meta` 字典；`meta` 只留给格式特有、暂不通用的信息。**暂不引入 `Segment` 嵌套抽象**——现在只有 src/tgt 各一段纯文本，等真的要支持一对多切分或富标记（TBX/SRT等）时再重构，现在加是过度设计。

```python
from dataclasses import dataclass, field

@dataclass
class TranslationUnit:
    src_lang: str
    tgt_lang: str
    src_text: str
    tgt_text: str
    guid: str | None = None          # 语料库格式自带guid时回填(如sdltm/tmx读入)，新生成时由writer填
    source_file: str | None = None
    source_key: str | None = None    # 原始编号/行号，供调试和QA报告使用
    created_at: str | None = None
    modified_at: str | None = None
    meta: dict = field(default_factory=dict)   # 格式特有/尚不通用的信息

@dataclass
class ParagraphPair:
    """双语原文件里，对齐前的一对整段/整行文本。"""
    key: str            # 原始编号 / 行号，用于报缺失警告
    src_text: str
    tgt_text: str
```

**架构约束（必须写测试守护）**：对齐算法绝不允许跨 `ParagraphPair` 边界做统一 DP——每个 `ParagraphPair` 必须独立对齐，不能把整篇文档拼成一条序列去跑。现有脚本的 `align_pairs` 实际上已经是按 key 逐段对齐的，这里只是把它明确成硬性架构约束并要求 Phase 1 补一条回归测试断言这一点（防止未来"性能优化"时被悄悄破坏）。

---

## 3. 接口契约 (`corpustools/interfaces.py`)

```python
from typing import Protocol

class BilingualReader(Protocol):
    """双语原始文件 → 段落级 ParagraphPair 列表（未拆句）"""
    def read(self, path: str, **opts) -> list[ParagraphPair]: ...

class CorpusReader(Protocol):
    """语料库文件 → 句子级 TranslationUnit 列表（已经是最终粒度）"""
    def read(self, path: str) -> list[TranslationUnit]: ...

class CorpusWriter(Protocol):
    """TranslationUnit 列表 → 语料库文件"""
    def write(self, path: str, units: list[TranslationUnit], **opts) -> None: ...
```

所有 reader/writer 都是无状态函数式模块，禁止在模块级存全局可变状态（现有脚本里 `REPAIR` 全局字典这种写法，重构时要改成参数传递或类实例，避免多次转换互相污染——这是现有代码唯一需要在重构时顺手清理的坏味道）。

---

## 4. 目录结构

```
bi-corpus-tools/
├── corpustools/
│   ├── model.py            # TranslationUnit, ParagraphPair
│   ├── interfaces.py        # Protocol 定义
│   ├── align/
│   │   ├── splitters.py     # split_en / split_zh / pick_splitter (从现有脚本迁移，含已修的语言方向bug修复)
│   │   ├── repair.py        # 文本修复规则加载 (repairs.json)，去掉全局可变状态
│   │   └── aligner.py       # DP 对齐算法 (align_pairs 泛化版，输入 ParagraphPair 列表)
│   ├── readers/
│   │   ├── docx_numbered.py # 现有 [1]..[N] 编号版式
│   │   ├── docx_table.py    # 新增：表格版式
│   │   ├── xlsx_bilingual.py
│   │   └── csv_bilingual.py
│   ├── corpus_readers/
│   │   ├── tmx_reader.py    # Phase 3
│   │   └── sdltm_reader.py  # Phase 3
│   ├── writers/
│   │   ├── sdltm_writer.py  # 现有 write_sdltm 迁移，DDL/schema 不变
│   │   ├── tmx_writer.py
│   │   └── csv_writer.py    # 人工审阅用
│   └── cli.py                # Phase 4 统一入口，本阶段先保留旧CLI跑通即可
├── tests/
│   ├── fixtures/             # 各格式的最小合成样本文件
│   └── test_*.py
├── pyproject.toml
└── README.md
```

---

## 5. Phase 0 — 建立回归基线（先于任何重构）

**在动 Phase 1 之前先做这一步。** 用现有 `reference/docx_to_sdltm_v1.py` 对一组精心挑选的 fixture docx（含缩写句号场景、编号缺失场景、正向/反向语言方向）跑一遍，把输出**语义内容**（不是原始文件本身）固化成 `tests/fixtures/expected/*.json`，作为 Phase 1 起重构的判定基准。

**已实测确认（不是推测）**：同一份输入连续跑两次 `docx_to_sdltm_v1.py`，`.sdltm` 和 `.tmx` 输出都不是字节一致的——guid 用 `uuid.uuid4()` 随机生成，时间戳用 `datetime.now()`，两个格式的 header/记录里都嵌了这些运行时值。**只有 csv 输出是真正确定性的**。所以：

- csv：可以要求逐字节一致
- sdltm/tmx：必须做**语义等价**比较——把输出重新读回来（用 Phase 3 才会写的 corpus reader，Phase 0/1 阶段可以先写一个内部专用的最小读取校验函数，不用等 Phase 3 完整实现），比较 `src_lang`/`tgt_lang`/`src_text`/`tgt_text`，guid/时间戳这类易变字段直接排除比较

## 6. Phase 1 — 模块化重构（不改变行为）

把 `docx_to_sdltm.py` 按上面目录拆开，对照 Phase 0 固化的基线验证输出语义不变。

**验收标准**：
- 按 Phase 0 的语义等价方法比较，不是字节比较（sdltm/tmx 字节比较在架构上就不可能通过，见上）。
- `align_pairs` 的签名从 `(src, tgt, keys, src_lang, tgt_lang, ...)` 改成接受 `list[ParagraphPair]`，输出 `list[TranslationUnit]`，并保证严格按 `ParagraphPair` 分组独立对齐（见第2节的架构约束），补一条测试断言这一点。
- `pick_splitter` / `is_cjk_lang` / `looks_cjk` 逻辑原样保留（已验证过双向语言场景）。
- 顺手把 `docx_numbered.py` 的底层文本抽取从纯正则迁移到共享的 `readers/_ooxml.py`（`xml.etree.ElementTree` 实现的段落/表格 walker），为 Phase 2 的 `docx_table.py` 复用打基础；这个迁移必须在 Phase 0 基线保护下进行，只允许提取方式变、行为不能变。
- 去掉现有脚本里 `REPAIR` 这类模块级全局可变状态，改成参数传递或类实例，避免多次转换互相污染。

---

## 7. Phase 2（优先）— 扩展双语源格式

### 6.1 xlsx reader (`readers/xlsx_bilingual.py`)

- **改用 `openpyxl` 作为常规依赖，不再坚持纯 stdlib 手写解析。** 之前"零依赖"的判断是从 image-optimizer 等项目的模式简单类推过来的，但那些项目避的是重量级/带二进制编译的依赖，openpyxl 是纯 Python、对 PyInstaller 打包没有额外负担。真实世界的双语 xlsx 远比"sheet1.xml + sharedStrings.xml"复杂——合并单元格、内联字符串（inline strings）、富文本、日期单元格这些手写解析器迟早会踩到，没必要重新发明一遍 openpyxl 已经踩过的坑。
- 默认约定：前两个非空列 = 源 / 译文，每一行 = 一个 `ParagraphPair`（key = 行号）。
- 参数：`--src-col`/`--tgt-col`（列字母，如 A/B）覆盖默认；首行若像表头（内容为语言名/"源文"/"译文"等，或纯字母无法转换）则自动跳过，也支持 `--header` / `--no-header` 显式指定。
- 空单元格：一侧为空则跳过该行并打印警告（复用 Phase 0 里 `find_blocks` 已经建立的"编号缺失打警告"模式）。

### 6.2 csv/tsv reader (`readers/csv_bilingual.py`)

- 用 stdlib `csv` 模块，分隔符默认自动嗅探（`csv.Sniffer`），提供 `--delimiter` 覆盖。
- **编码是最大的坑**：国内 Excel 导出的 CSV 经常不是 UTF-8，也可能带 UTF-8 BOM。读取时按 `utf-8-sig` → `utf-8` → `gb18030` 顺序尝试（用 GB18030 而不是 GBK 兜底，GB18030 是 GBK 的严格超集，覆盖面更大且没有额外成本），失败给出明确报错而不是乱码静默通过。
- 其余约定同 xlsx（双列、表头检测、缺失警告）。

### 6.3 docx 表格版式 reader (`readers/docx_table.py`)

- 现有 `docx_paragraphs()` 是纯正则抠 `<w:t>`，对表格结构（`w:tbl/w:tr/w:tc`）不友好。这部分建议改用 `xml.etree.ElementTree` 配合 word 命名空间解析表格的行/列结构（段落内文本抽取仍可复用正则或简单的 findall），别在正则上继续叠字符串黑魔法。
- 约定：2 列表格 = 源|译文；≥3 列时默认取最后两列，同时提供 `--src-col-index`/`--tgt-col-index`（0-based）手动指定。
- **必须支持自动识别版式**：文档里有合格的双列/多列表格 → 表格模式；否则退回现有编号版式逻辑。也提供 `--layout {numbered,table}` 手动覆盖自动判断，防止误判。

### 6.4 每个新 reader 的强制测试项

- 最小合成 fixture（2-3 行内容，含一个中英文混排的边界情况）
- **语言方向反转测试**：`--src`/`--tgt` 对调后结果必须正确重新分句/拼接（这是 Phase 0 里真实踩过的坑，必须对每个新格式重复验证，不能假设"docx 修好了 xlsx 就一定没事"，因为 xlsx/csv reader 是全新代码路径）
- 缺失行/空单元格场景，确认警告输出且不崩溃
- csv 额外测：GBK 编码样本文件必须能正确读取

---

## 8. Phase 3 — 语料库互转 (tmx ↔ sdltm)

- `corpus_readers/tmx_reader.py`：标准 TMX（`<tu><tuv xml:lang=...><seg>`），用 `xml.etree.ElementTree` 解析，直接产出 `TranslationUnit` 列表（无需过对齐算法）。
- `corpus_readers/sdltm_reader.py`：`sqlite3` 查询 `translation_units` 表，`source_segment`/`target_segment` 是现有 `seg_xml()` 包出来的一段 XML，需要写对应的反解析函数把 `<Value>` 里的文本抠出来（`writers/sdltm_writer.py` 里的 `esc()` 要配一个 `unesc()`）。
- 互转本质是 `corpus_reader.read() → corpus_writer.write()`，一行代码量级，但测试要覆盖：tmx→sdltm→tmx 往返后文本内容不丢失/不重复转义。

### SDLTM 兼容等级（必须在代码注释和 README 里明确写出，避免误解）

`sdltm_writer.py` 不是一个普通的"往 SQLite 里插数据"的 writer，它本质是一个 **Trados 专用后端**，目标定位需要写清楚是哪一级：

- **Level 1 — 结构兼容**：表结构、字段符合 Trados 私有 schema，SQLite 文件本身合法
- **Level 2（本项目目标）— Studio 可读可导入**：Trados Studio 能正常打开、显示、编辑这个 TM；`fuzzy_data` 表留空是已知的、有意为之的限制——Studio 首次使用时会自己重新计算模糊匹配索引
- **Level 3 — 原生等价**：`source_hash`/`fuzzy_indexes` 与 Trados 私有的、基于词干化的哈希算法位级一致

本项目**明确不追求 Level 3**（Trados 的私有哈希算法未公开，逆向出来性价比很低），文档里要写清楚这一点，避免使用者误以为生成的 TM 在模糊匹配检索性能上等价于 Studio 原生生成的 TM。

## 9. QA 层（Phase 2 起逐步加入，不是独立后置阶段）

在 Align 和 Writer 之间插一层轻量 QA，把 `csv_writer.py` 从单纯的"人工审阅导出"升级成真正的对齐质量报告。**v1 范围克制一点**，先做四项，别一次上齐：

- 源文/译文为空（GAP）
- 长度比异常（DP 对齐本身已经算出了长度比代价，直接从对齐结果里取出来暴露即可，不用重新计算）
- 重复 TU（同一 src_text 对应不同 tgt_text，或反之）
- 数字不匹配（源/译文里出现的阿拉伯数字集合不一致，常见的漏译/多译信号）

标签/占位符/URL 匹配这类检查最初先不做——当时输入都是纯文本段落，还没有 inline tag 场景，加了也是没有实际输入可测的空中楼阁。**现已补上**（TM 维护模块之后的一轮）：`tmx_reader` 已经能解析 `<bpt>/<ept>/<ph>/<hi>` 等 inline 标签并填充 `TranslationUnit.src_markup`/`tgt_markup`，有了真实可测的输入，于是加了三项：

- `TAG_MISMATCH`：比较 src/tgt 两侧 inline 标签的**类型计数**（比如各有一对 bpt/ept）。刻意不检查顺序和 id 配对——译文为适应目标语语序调整标签位置是正常现象，不该被判定为缺陷；真正丢标签/多标签（计数对不上）才会被抓到。两侧都没有 markup 时直接跳过（纯文本 TU 的常态）。
- `PLACEHOLDER_MISMATCH`：比较可见文本里的占位符 token 集合（`{name}`、`{0}`、`%s`、`%(name)s`），大小写敏感、精确匹配——占位符是代码不是文字，必须原样保留。
- `URL_MISMATCH`：比较 `http(s)://` URL 集合，译文丢链接或改错链接都会被抓到，不做模糊容忍。

测试用例见 `tests/test_qa.py`（含 `tests/fixtures/tmx/inline_markup_qa.tmx` 这份手写的、带真实 inline markup 的 TMX fixture，端到端跑一遍 `tmx_reader.read()` + `qa.run()`）。

QA 结果作为 `TranslationUnit.meta['qa_issues']` 附加在每条 TU 上，`csv_writer.py` 增加 `confidence`/`status`/`issues` 列输出。

---

## 10. Phase 4 — 统一 CLI，薄薄一层包在 Python API 上

**先把 Python API 定下来，CLI 只是它的一层薄封装**，这样以后 Phase 5 的 GUI 也调用同一个 API，不用重新实现一遍管线：

```python
from corpustools import convert

convert("input.docx", "output.tmx", src_lang="en-US", tgt_lang="zh-CN")
```

`biconvert input.xxx output.yyy [--src ..] [--tgt ..] [--layout ..]` 内部就是调这个 `convert()`，按扩展名路由 reader/writer，docx 自动判断版式。等 Phase 2/3 落地后再细化参数设计。

---

## 11. Phase 顺序总览

- **Phase 0** — 固化现有脚本行为的回归基线（golden fixtures + 语义等价比较方法），先于任何重构
- **Phase 1** — 模块化重构 + 数据模型/接口定型 + docx_numbered 迁移到共享 OOXML walker，对照 Phase 0 基线验证无行为漂移
- **Phase 2（优先级最高）** — 新增双语源格式：docx 表格版式、xlsx（openpyxl）、csv/tsv，QA 层从这一步开始逐步引入
- **Phase 3** — 语料库互转：tmx reader、sdltm reader，明确 SDLTM Level 2 兼容目标
- **Phase 4** — 统一 CLI，包装已经定型的 Python API
- **Phase 5** — 桌面 GUI 工具箱，见第 13 节（已确定要做，架构已定，非"可选待定"）

---

## 12. 交付与协作方式

- 走既定流程：opencode 在新仓库的 `dev` 分支实现，GitHub 作为同步媒介，Claude 后续负责审查 + 出 patch。
- 仓库：`aREversez/laelaps`（原名 `language-tools`，仓库已重命名，Python 包导入名 `language_tools` 不受影响）。GUI 工具箱和核心库同仓库，不拆独立仓库（见第13节）。
- 每个 Phase 建议拆成独立 PR/commit 序列，不要把 Phase 1 重构和 Phase 2 新功能混在一次提交里（符合"一次提交一个语义改动"的既有约定）。
- Phase 0 的基线必须先跑通、Phase 1 对照基线验证语义不变之后，再开始 Phase 2，避免在不稳定的地基上加新 reader。

---

## 13. Phase 5 — 桌面 GUI 工具箱

### 定位

这个项目的终局不是"docx转sdltm的库"，而是**语言管理（翻译/本地化等）工具箱**——语料转换只是第一个工具，以后会陆续加术语管理、QA报告查看器等。所以 GUI 从一开始就要按"壳 + 可插拔工具"的结构设计，不能做成绑死单一功能的界面。

**不做 Web UI**（不是 FastAPI+浏览器那套），做**原生桌面应用，打包成 exe**。技术选型 **PySide6**（Qt for Python）：
- 侧边栏导航 + `QStackedWidget` 天然适合"一个壳、N个工具页"这种会持续长大的结构
- 以后工具如果需要复杂数据展示（比如 QA 报告要能排序筛选），Qt 的 `QTableView` 比其他轻量方案能力强得多
- PyInstaller 打包 PySide6 是成熟路径

代价：包体积比 tkinter 系方案大。如果以后发现这是实际痛点，CustomTkinter 是轻量备选，但届时要重新评估迁移成本。

### 架构：壳与工具解耦

```
toolbox/                    # 与 language_tools/ 同仓库同级，GUI层
├── main.py                 # 入口: python -m toolbox.main
├── main_window.py           # MainWindow: 侧边栏 + QStackedWidget，不感知具体工具
├── registry.py               # ToolSpec 数据结构 + register()/discover()
├── resources/                 # 图标、样式，未来共享设计规范放这里
└── tools/
    ├── corpus_convert/       # 第一个工具，包装 language_tools.api.convert()
    │   ├── __init__.py       # 注册 ToolSpec
    │   └── page.py            # QWidget 表单 + QThread worker（避免转换时卡UI）
    ├── tm_maintenance/       # 第二个工具，包装 language_tools.tm.*（清理/合并/统计）
    │   ├── __init__.py       # 注册 ToolSpec
    │   └── page.py            # 三个标签页（清理/合并/统计），共用一个通用 CallableWorker
    ├── qa_check/             # 第三个工具，包装 language_tools.tm.qa_report（对已有语料库跑 QA）
    │   ├── __init__.py       # 注册 ToolSpec
    │   └── page.py            # 结果表格 + 筛选（问题类型/只看有问题的）+ 导出 CSV
    ├── alignment_check/      # 第四个工具，包装 language_tools.align_report（对齐诊断预览，不写文件）
    │   ├── __init__.py       # 注册 ToolSpec
    │   └── page.py            # 文件 + 语言/排版三个控件合并成一行（AdjustToContents 让下拉框宽度贴内容，不再被 QFormLayout 撑满一整行）+ 结果表格（拿伸缩空间）+ 筛选 + 导出 CSV——原来三个输入区各占一整行，非全屏窗口下曾把结果表格挤到只剩一两行可见，见该文件 docstring
    └── <future_tool>/        # 新工具照此结构新增文件夹即可，main_window.py 不用改
```

`language_tools` 核心库完全不知道 GUI 的存在——`corpus_convert/page.py` 只是把它当依赖 `import`，直接调用 `api.convert()`（不经过 HTTP，纯函数调用），和 CLI 用的是同一个入口。这保证了：
- 核心库的回归测试（Phase 0-4 那一整套）完全不受 GUI 变动影响
- 新增工具不需要碰 `main_window.py`，只要新建文件夹 + 调用 `register(ToolSpec(...))`

### 工具契约

```python
@dataclass
class ToolSpec:
    id: str
    name: str
    description: str
    icon: str
    page_factory: Callable[[], QWidget]   # 返回这个工具的一个新页面实例
```

`registry.discover()` 在启动时用 `pkgutil.iter_modules` 扫描 `toolbox/tools/` 下所有子包并 import 一遍（触发各自 `__init__.py` 里的 `register()` 调用），`MainWindow` 只读 `registry.TOOLS` 渲染侧边栏，不硬编码任何具体工具。

### 转换耗时与线程

GUI 直接函数调用 `api.convert()`，为避免大文件转换时界面卡死，放进 `QThread`（`ConvertWorker`）跑，通过 Qt 信号（`finished_ok`/`finished_err`）把结果送回主线程更新界面。这个模式后续每个新工具但凡涉及可能耗时的操作都应该沿用，不要在主线程里跑重活。大多数工具的耗时操作没有各自独立的 kwargs 形状，所以用的是 `toolbox/workers.py` 里共享的 `CallableWorker`（接收任意零参数 callable）——`tm_maintenance`、`qa_check` 都用它，`ConvertWorker` 是唯一的例外，因为它专门对应 `api.convert()` 的 kwargs 签名。新工具的耗时操作如果也是"调一个函数、等结果"这种形状，直接复用 `CallableWorker`，不要再写一个专门的 Worker 子类。

### 测试

`QT_QPA_PLATFORM=offscreen` 环境变量可以让 Qt 在没有显示器的环境（比如 CI）里跑，配合 `pytest-qt` 的 `qtbot` fixture可以写真实的交互测试（点按钮、等信号、检查界面状态），不用退化成"只测非GUI逻辑"。已验证：包括一次端到端的真实转换（点转换按钮 → 等 QThread 完成 → 检查输出文件确实生成）都能在无头环境里测。

**坑**：任何用到 `QIcon`/`QSvgRenderer`/`QPixmap` 这类 GUI 相关类的测试，哪怕不创建任何 widget，也必须先有一个 `QApplication` 实例存在，否则进程直接 abort（不是抛异常，是段错误级别的崩溃，pytest 输出里看不到正常的 traceback）。写测试时统一让这类测试也接一个 `qtbot` fixture 参数（哪怕用不上它），靠 pytest-qt 保证 QApplication 已经建好，别自己手动 `QApplication([])` 到处建。

### 品牌资源与设计系统

`toolbox/resources/`：
- `style.qss` —— 全局样式表，Design tokens 都在这一个文件的注释里，新工具要用同样的颜色/间距直接引用这里定义的，不要在某个工具的 `page.py` 里重新写一遍色值
- `logo.svg` —— 应用 logo，"对齐标记"主题（两行不同长度的色块 + 细连接线），呼应核心技术概念（句级对齐），不是随便找的翻译类 icon
- `icons/<tool_id>.svg` —— 每个工具在侧边栏用的图标，新工具照此新增一个
- `icons/app.ico` —— Windows exe 图标，多分辨率（16/32/48/64/128/256），由 `logo.svg` 渲染成 256px PNG 后用 Pillow 转出来的，logo 改了要重新生成这个文件（脚本片段见 git log 里 "Add branding: logo, tool icon, QSS design system" 这次提交的过程，没有单独存成脚本，需要的话重新跑一遍：Qt渲染SVG到256px QImage → 存PNG → `PIL.Image.open(...).save('app.ico', format='ICO', sizes=[...])`）

Design tokens（颜色，命名 hex，别在别处重新定义）：
- `ink #1A1D23` 主文字 / `slate #6B7280` 次要文字 / `paper #F6F7F9` 背景 / `surface #FFFFFF` 面板与输入框 / `hairline #E3E6EB` 分隔线 / **`indigo #2E4374` 唯一强调色**（主按钮、选中态、焦点框）
- 语义色（`success #2F855A`/`danger #B23B3B`）只用于状态提示，不作装饰

排版：统一用系统字体（Segoe UI），不引入自定义字体文件——层级完全靠字重/字号区分，这是刻意的选择：桌面工具软件跟着平台走比"用两种字体撑个性"更合适，跟营销页/网站的设计诉求不一样。

布局原则：扁平面板 + 发丝级分隔线，不用 QGroupBox 原生的"盒子套标题"外观（做不出干净的现代感，`toolbox/widgets.py` 里的 `section()` helper 是替代方案：一个小标题 label + 一条分隔线 + 内容），不做千篇一律的"卡片+统一阴影"（SaaS 模板的典型味道）。

新工具的界面要保持一致性：优先复用 `toolbox/widgets.py` 里 `section()` 这样的现成 helper（以及耗时操作用 `toolbox/workers.py` 的 `CallableWorker`），主按钮统一用 `objectName('primaryButton')`（QSS 已经定义好了这个选择器），日志类输出用 `objectName('logConsole')` 的 `QTextEdit` 走富文本着色（`_log(message, kind='info'|'error'|'success')` 这个模式），不要每个工具各写一套。

### 打包

`packaging/language-toolbox.spec`（PyInstaller spec，已提交到仓库，可复现构建）：
```bash
pip install -e ".[gui]"
pyinstaller packaging/language-toolbox.spec
```
默认 `onedir`（启动更快、方便排查缺失依赖），`ONEFILE=True` 切换成单文件 exe。已经在 spec 里把 `toolbox/resources/` 加进 `datas`，并指定了 `icon=...app.ico`（Windows/macOS 才生效，Linux 打包时会有一条"Ignoring icon"的提示，正常，不是错误）。

**已经在打包链路上踩过一个坑并修复**：`toolbox/main.py` 作为 PyInstaller 的入口脚本，冻结后它自己的 `__file__` 解析方式和被正常 import 的子模块不一样——之前 `main.py` 里用 `os.path.dirname(__file__)` 算资源目录，源码跑没问题，但打包成 exe 之后会报 `FileNotFoundError`（实测复现过），因为冻结后入口脚本的 `__file__` 丢失了 `toolbox/` 这层路径前缀。修复方式是把路径计算挪到一个单独的、永远以普通模块方式被 import 的文件（`toolbox/paths.py`），入口脚本和其他模块都从这里拿 `RESOURCES_DIR`，不要自己在入口脚本里现算。**这提醒了一件事：涉及路径解析的改动，必须实际跑一遍 PyInstaller 打包后的产物验证，不能只在源码环境测试就认为没问题**——本项目源码环境的测试当时是全绿的，问题只在实际冻结后的可执行文件里才暴露。

**PyInstaller 不能跨平台编译**，最终的 Windows exe 必须在 Windows 上跑这条命令产出；本项目在 Linux 沙盒里跑通过同一份 spec（产出 Linux 二进制，成功启动，资源文件路径解析也验证过没问题），验证的是打包链路本身没有缺失依赖/隐藏 import/资源路径这类问题，不是最终 Windows 产物本身。

**又踩了一个坑，这次是隐藏 import，且是真·被漏掉的那种（不是上面说的"验证过没问题"）**：`toolbox/registry.py` 的 `discover()` 用 `pkgutil.iter_modules()` 扫出 `toolbox/tools/` 下的子包名，再用 `importlib.import_module('toolbox.tools.%s' % name)` 拼一个**运行时才确定**的字符串去 import——这正是 registry.py 文档字符串里强调的"新增工具只需要新建文件夹，`main_window.py` 不用改"那份优雅，但 PyInstaller 的静态分析（`Analysis`/modulegraph）只能识别字面量形式的 import/`importlib.import_module('固定字符串')`，一个运行时拼出来的模块名它看不见。后果：`alignment_check`/`corpus_convert`/`qa_check`/`tm_maintenance` 四个子包从来没有被真正打进 PYZ 归档（用 `PyInstaller.archive.readers` 直接读打包产物的 TOC 验证过：`hiddenimports=[]` 时归档里只有 `toolbox.tools` 这个空壳包，四个真正的工具子包完全不存在），冻结后应用启动时 `discover()` 在自己那份空壳里扫不出任何东西，`MainWindow` 落到"没有已注册的工具"的空状态分支——侧边栏和内容区都是空的，正是用户反馈的现象。这个 bug 本身跟操作系统无关（modulegraph 的静态分析在 Linux/Windows 上行为一致），只是之前"在 Linux 沙盒里验证过"大概率验证的不是真正启动冻结产物的效果，才没有及时发现。

修复方式是在 `packaging/language-toolbox.spec` 里显式提供 `hiddenimports`：`packaging/pyinstaller_hooks.py` 里的 `collect_tool_hiddenimports()` 在打包时（普通、未冻结的 Python 进程里，`pkgutil` 正常工作）调用 `PyInstaller.utils.hooks.collect_submodules('toolbox.tools')`，把 `toolbox/tools/` 下所有子包的完整点分路径显式列出来传给 `Analysis(hiddenimports=...)`，且以后新增工具文件夹不需要再手动改这个列表（`collect_submodules` 在每次打包时重新扫一遍）——保持了 registry.py 文档字符串许下的"新增工具不用碰其它代码"的承诺，只是把满足这个承诺的机制从"假设 PyInstaller 能自己看懂"挪到了打包脚本这一层。该函数如果发现某个 `toolbox/tools/<id>/` 包没有出现在 `collect_submodules()` 的结果里，会直接抛 `RuntimeError` 让打包失败，而不是安静地产出一个"能跑起来但工具是空的"exe——`tests/test_packaging_spec.py` 对这个函数（包括这个失败分支）有单测覆盖，不需要真的跑一遍 PyInstaller 就能在日常测试里发现类似问题。

### 已知的验证盲区：字体和原生控件渲染

**Linux 沙盒开发环境验证不了 Windows 上的字体/控件渲染效果**，这是本项目开发过程中吃过一次真实的亏：字体栈最初写的是 `"Segoe UI", "PingFang SC", sans-serif`——Segoe UI 不含中文字形，PingFang SC 是 macOS 专属字体在 Windows 上根本不存在，结果 Windows 上中文实际走的是某个未声明的兜底字体，且不同控件解析到的兜底字体不一致，出现"某个字突然变粗"这类字重错乱的观感问题（用户在真机截图里发现的，沙盒里的离屏渲染完全看不出这个问题，因为 Linux 环境装的是别的中文字体，不会触发 Windows 特有的字体替换链）。

已修复为 `"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", "PingFang SC", sans-serif"`（Windows 中文应用的标准选择），复选框指示器和下拉框箭头也从"CSS三角形技巧"/"原生渲染"换成了自绘 SVG 图标（`icons/checkbox_checked.svg`、`icons/checkbox_unchecked.svg`、`icons/chevron_down.svg`），避免依赖平台原生控件渲染的不确定性。**这些改动本身的正确性有把握（是 Windows 中文桌面应用的标准做法），但视觉效果本身没有、也没法在这个沙盒环境里用真实 Windows 机器肉眼确认**，需要在真机上跑一遍确认。以后任何"看起来是字体/原生控件渲染"的问题，都要假设沙盒环境验证不出来，直接问用户要真机截图确认，不要凭 Linux 离屏渲染的结果下结论。

**同一类问题在 `tm_maintenance` 工具上又踩了一次（真机截图确认后修的）**：`QTextEdit#logConsole` 最初的字体栈是 `"Cascadia Code", "Consolas", "Microsoft YaHei UI", monospace`——Consolas/Cascadia Code 都不含中文字形，日志区里中文提示文字（"清理完成"之类）实际走的是 Windows 未声明的兜底字体，跟界面其它地方用的 Microsoft YaHei UI 不一致，表现为用户反馈的"一会儿衬线一会儿无衬线"。根因和上面 Segoe UI 那次一模一样：字体栈里塞了一个不含 CJK 字形的字体在前面。已改成跟全局一致的中文优先无衬线栈，不再单独给日志区用等宽/代码字体。**这提醒一件事：任何"看起来该用等宽字体"的场景（日志、路径、数字），只要这个区域可能显示中文文字，都不能简单套用纯 ASCII 的 monospace 字体栈，CJK 字形必须排在前面或者干脆放弃等宽（本项目选择了后者）。**

`QTabWidget`/`QTableWidget` 是这一轮（`tm_maintenance` 的清理/合并/统计三个标签页 + 统计结果表格）第一次在这个项目里用到，`style.qss` 里新增的 `QTabBar::tab`/`QHeaderView::section` 等规则跟其它控件一样，只在 Linux 离屏渲染里验证过"没有崩溃、属性生效"，视觉效果（选中态的颜色对比度、圆角是否跟 pane 衔接自然）同样需要真机截图确认。

### 后续工具接入的最小步骤

1. `toolbox/tools/<new_tool_id>/` 新建文件夹
2. `page.py` 写一个 `QWidget` 子类作为这个工具的界面，需要调用某个库就直接 `import`
3. 涉及耗时操作照抄 `ConvertWorker` 的 `QThread` + 信号模式
4. `__init__.py` 里 `register(ToolSpec(id=..., name=..., description=..., icon=..., page_factory=YourPage))`
5. 不需要碰 `main_window.py`、`registry.py`、其他工具的任何代码

---

## 14. 定位再澄清：语言服务管理工具箱，不止语料/术语

第 13 节开头那句"语料转换只是第一个工具，以后会陆续加术语管理、QA报告查看器等"当时举的例子有限，容易让人以为工具箱的边界就是"语料库 + 术语库"。**实际边界更宽**：只要是语言服务（翻译/本地化）工作流程里，译者/项目经理会反复手动做、值得写成一个独立工具页的事，都在范围内——不局限于语料和术语这两类，本文档后续新增的工具条目不需要现在就归类到某个固定分类下。

第 15 节的 backlog 已经不只是"语料类"条目（批量处理、TM 条目编辑器、杠杆分析属于语料；术语管理是新的一类；HTML/PDF 报告导出、常用设置记忆则是横切各工具的体验优化，不专属任何一类）。以后再冒出新方向（比如项目/报价/供应商相关的小工具）不需要先讨论"这算不算语言管理工具箱该做的事"，只要符合"壳 + 可插拔工具"架构（第 13 节）、有真实使用场景，直接按第 13 节末尾"后续工具接入的最小步骤"接进来即可。

---

## 15. Backlog（未排期，按讨论时间顺序记录，不代表优先级）

供后续排期参考，**不是承诺的交付顺序**——具体做哪个、什么时候做，看实际需求出现的频率决定。真正要做时需要单独展开设计（数据模型、格式选型、Phase 划分），参考本文档其它 Phase 的详细程度。下面先列未开始的条目，已完成的列在后面“已完成”子节就地归档。

- **TM 条目级浏览/编辑**：清理/合并/统计都是批量操作，没有条目粒度的"打开一个 TM，浏览/手动改或删单条"界面，现在只能导出 CSV 改完再重新导入，一来一回没有直接编辑方便。（【TM 编辑】页已实现条目级浏览/编辑/去重，但"打开已有 TM 文件"的入口仍按当初设计暂缓——编辑结果走导出落盘）

### 已完成（从上面的 backlog 毕业，就地归档；术语管理单独见 15.1）

- **对齐检查/术语一致性检查报告的 HTML/PDF 导出** ✅（2026-09）：`language_tools/reports/adapters.py` 补了 `from_align_summary()`/`from_term_summary()` 两个适配器（一节一个，形状跟着对应的 `summarize()` 走），`language_tools/reports/render.py` 基本不动——格式分发本来就是按扩展名，html/pdf 一套通用；唯一的实质改动是 PDF 分支改用 reportlab 内置的 CJK CID 字体（STSong-Light），因为这两个适配器是第一批往报告里填中文内容的（对齐类型标签、术语译文），默认 Helvetica 的 WinAnsi 编码会把它们渲染成空白。CLI：`tmtool align`/`tmtool term-check` 加 `--report PATH`，跟 `qa`/`leverage`/`compare` 已有的完全同一套约定。GUI：【对齐检查】【术语管理·一致性检查】两个页面加"导出报告…"按钮，照抄【QA 检查】页已经定下来的同步 `report_render.write()` 模式（一次小汇总，不值得开 worker 线程）。术语报告命中表按"词对 × 检查方向"聚合，`approved` 方向的行标 `Approved missing`，不与 `forbidden` 混行。测试见 `tests/test_reports_adapters.py`、`tests/test_tm_cli.py` 及两个页面各自的 GUI 测试。
- **批量对齐检查** ✅（2026-09）：`toolbox/tools/batch_alignment_check/` 新工具页。"批量转换"那半边其实早就存在（【批量转换】页，当初从【语料转换】页拆出来的多文件列表 + 添加/移除/清空控件），这次补的是缺的那半边：多选文件/文件夹 → 逐文件跑 `align_report.run()` → 表格逐行报告。复用批量转换已经验证过的专属 `QThread` worker 模式（`file_done`/`all_done` 信号逐行更新进度，不是 `CallableWorker`——那是一次性回调，撑不起逐文件进度）；每行三态：对齐正常（绿）/ 需检查（红，GAP 或 QA 标记）/ 检查失败（红，带原因），可导出汇总 CSV（`file,units,gap_count,qa_flagged,status`）。shell 循环（`tmtool align --fail-on-issues`）继续保留给脚本场景，两者不互相替代。

### 15.1 术语管理（Phase G0-G2 已完成，G3 完成一半，2026-09）

**目标**：维护一份双语术语表，并能拿它去对照一个已有 TM（tmx/sdltm）做术语一致性检查——这是术语库在翻译工作流里最直接的价值：不是"存一堆词"，是"存的词能真的用来抓问题"。

**数据模型**（`language_tools/terms/model.py`，与 `TranslationUnit` 同样的"已知字段类型化，不塞进 meta"原则）：

```python
@dataclass
class TermEntry:
    src_lang: str
    tgt_lang: str
    src_term: str
    tgt_term: str
    status: str = 'approved'   # 'approved' | 'forbidden' -- 见下方"为什么要分两档"
    domain: str | None = None  # 领域/项目标签，可选
    note: str | None = None
    guid: str | None = None
    source_file: str | None = None
    created_at: str | None = None
    modified_at: str | None = None
```

**为什么要分 `approved`/`forbidden` 两档，而不是只有一份"标准译法"表**：术语检查真正有实用价值、且几乎不会误报的场景是"这个词绝对不能这样翻"（`forbidden`——比如某客户明确禁用的旧译名、容易和相似术语混淆的错误译法）；"这个词应该用标准译法"（`approved`）看似更直觉，但检查逻辑上风险大得多——译文用同义词、代词回指、语序调整都是合法翻译，拿"译文里有没有出现这个词"去判断"标准译法有没有用"极易大量误报。所以**v1 范围克制**（延续 `qa.py` 当初"先做四项，别一次上齐"的做法）：只做 `forbidden` 方向的检查。`approved` 方向后来在 Phase G3 落地了，但当初的担心没有被推翻，所以实现方式正是按这个判断来定的：**默认关闭、显式 opt-in**（`run(units, glossary, check_approved=False)`），命中结果定位为"待核实提示"而不是缺陷判定（所有下游呈现——CSV/GUI/报告——都给这类命中标上"未用推荐译法"字样），匹配策略也刻意不做任何模糊匹配，用的还是和 `forbidden` 一样的精确子串/词边界判断。

**存储格式**：v1 用 csv/xlsx，编码兜底沿用 `readers/csv_bilingual.py` 的 `utf-8-sig → utf-8 → gb18030` 顺序。落地实现比最初设想的六列更精简：文件本身只存 `src_term,tgt_term,status,domain,note` 五列，`src_lang`/`tgt_lang` 不落盘（一份术语库文件按惯例只对应一个语言对，跟 TM 一样，逐行重复没意义——见 `language_tools/terms/glossary.py` 模块文档），`guid`/`source_file`/`created_at`/`modified_at` 留在 `TermEntry` 上但读写都不涉及，是给后续阶段（比如合并多份术语库）预留的字段，不是当前格式的一部分。表头**要求**具名列（`src_term`/`tgt_term` 必须出现，大小写不敏感），不猜位置——术语表跟双语语料不一样，猜位置的启发式（`readers/_rowreader.py` 的 `looks_like_header()`）在这里根本分不出哪行是表头哪行是数据。TBX（MultiTerm 等 CAT 工具的术语交换标准格式）互通仍是后续阶段的目标，未实现。

**Phase 划分（实际完成情况）**：

- **Phase G0 — 术语库读写** ✅：`language_tools/terms/glossary.py`，`read(path, src_lang, tgt_lang)` / `write(path, entries)`（跟最初方案里的函数名 `read_glossary`/`write_glossary` 不同，去掉了重复的 `glossary` 前缀，模块名本身已经说明白了），csv/xlsx 两种格式。测试见 `tests/test_terms_glossary.py`（round-trip、表头校验、状态兜底、gb18030 编码、不支持的扩展名）。
- **Phase G1 — 一致性检查** ✅：`language_tools/terms/check.py`，`run(units, glossary)`，只做 `TERM_FORBIDDEN`（精确子串匹配；中日韩语言按字符子串匹配，拉丁字母语言按大小写不敏感的词边界匹配，复用 `align/splitters.py` 的 `is_cjk_lang`），结果写进 `TranslationUnit.meta['term_issues']`，独立于 `qa_issues`。额外加了 `summarize()`（同 `qa_report.summarize()` 的形状，去掉 `by_type`——术语命中没有固定的可枚举代码）。顺带接进了 `tmtool term-check`（`--glossary`/`--export`/`--fail-on-issues`，跟 `tmtool qa`/`tmtool align --fail-on-issues` 是同一套约定），`csv_writer.write()` 加了 `include_terms=True`。测试见 `tests/test_terms_check.py`、`tests/test_tm_cli.py`。
- **Phase G2 — GUI 工具** ✅：`toolbox/tools/term_management/`，两个标签页。「术语库」：术语表增删改走 `_TermEntryDialog`（模态表单，不是原地单元格编辑——见该模块文档，表单还多一层"提交前校验"，原地编辑没有等价的检查点）+ 导入/导出 csv/xlsx；语言对是页面级的两个下拉框（`compact_combo()`/`labeled_field()`，`toolbox.widgets`），不是每行都填。「一致性检查」：选一个 TM + 一份术语库 → 跑 Phase G1 → 结果表格，UX 基本照抄【QA 检查】页（筛选 + 导出完整 CSV），比 QA 检查少一个"按问题类型筛选"下拉——术语命中没有固定类型可选。测试见 `tests/test_toolbox_term_management_page.py`。
- **Phase G3（部分完成，2026-09）**：`approved` 方向的检查 ✅ —— `check.run()` 加 `check_approved` 参数（默认 `False`，理由见上方"为什么要分两档"），命中规则与 `forbidden` 对称：原文出现 `src_term` 且译文**没有**出现 `tgt_term` 即命中；另有两道防噪声闸门——译文为空的条目不命中（空译文是 `qa.py` 的 `EMPTY_TARGET` 的职责，不是"改写了"的证据；术语行 `tgt_term` 为空同样跳过），且只有 `status` 显式声明为 `approved` 的行参与（`TermEntry.status_declared`；`glossary.read()` 对留空/无法识别的 status 仍兜底为 `approved` 但标记为未声明，免得整份没填状态列的老术语表在勾选瞬间变成待核实清单）。每条命中带 `status` 键标明来源方向，`summarize()` 相应加 `by_status`（只列非零方向，同 `qa_report` 约定；对未经 `run()` 的 units 和无 `status` 键的旧命中用 `.get` 兜底，保持改动前的容错语义）。接入面：`tmtool term-check --check-approved`（打印按方向拆分）、CSV 列与 GUI 命中列前缀"未用推荐译法"、【术语管理】一致性检查标签页"同时检查推荐译法未使用"复选框（改的是检查计算本身，所以放在检查按钮旁而不是结果筛选行；状态经设置持久化）。TBX 导入导出：仍未开始，继续后置。

### 15.2 语言服务工作流路线图（角色 × 缺口分析，未排期，2026-09）

对现有 8 个工具按"哪个角色在哪个环节重复手动劳动"做了一次盘点：PM/销售售前的报价与译前评估、术语库的冷启动，是当前完全空白或最薄弱的两处（译员/审校的 QA 与术语查询、语言资产负责人的 TM 清洗与盘点、本地化工程师的格式互转都已有工具覆盖）。以下条目延续第 15 节"未排期、看实际需求频率决定"的原则，仅记录相对优先级和已识别的风险点，不是排期承诺。

**优先级判断标准**（沿用第 15 节精神，具体化为三条）：(a) 有角色每周都在手动重复；(b) 离线可做，不违背 README 的"不联网、不上传文件"定位；(c) 能复用现有 reader/writer、`align_report`、`leverage.py`、报告 adapter、`QThread` worker、插件式工具页注册等基础设施，而不是另起一套。

**第一优先**：

- **字数统计 + 加权工作量估算（报价器）** ✅（2026-09）：`language_tools/tm/quote.py` + `tmtool quote`，实现方式与预判一致，落地时把"风险"里提到的顾虑直接做成了产品约束而不是留言提醒——`DEFAULT_WEIGHTS` 在模块 docstring 和 `--weights` 帮助文本里都明确标注"仅为示例惯例，非行业标准，落地前须核对真实费率表"，`--weights` 接受 JSON 费率表覆盖默认值，未知档位/超范围权重直接报错而不是静默算错价。批次输入按扩展名分发（双语源文件走 `align_report.run()`，已转换的 `.tmx`/`.sdltm` 走 `tm_io.read_corpus()`），一批可以混着来，对应 PM"部分文件已转语料、部分还是原始双语稿"的真实场景。测试见 `tests/test_tm_quote.py`、`tests/test_tm_cli.py`。
- **术语提取（term extraction）** ✅（2026-09，范围收窄，见下方"实际做出来的边界"）：`language_tools/terms/extract.py` + `tmtool term-extract`/`term-extract-promote`。落地过程证实了"风险"栏的判断——统计方法精度确实有限，所以最终形态从"单语 n-gram/TF-IDF → 直接入库"收窄成两段式：`term-extract` 只产出候选审核表（`decision` 列默认全空），`term-extract-promote` 只提升审核表里显式标了 `decision=approve` 的行，两者中间隔着一次人工决定——没有任何路径能让候选词绕过这道人工闸门直接写进 `glossary.write()`。**实现方式和已知边界**（模块 docstring 里的完整版本，供实现细节参考）：
  - 单语候选：非 CJK 语言按空白分词做 n-gram + 词频，CJK 语言按字符滑窗 n-gram + 一个简化的"内部结合度"过滤（不是严格意义上的互信息 PMI，docstring 里特意没有用 PMI 这个名字，因为没有做语料级概率归一化）；两种语言都不做词形归一化/大小写折叠。
  - 双语配对（`suggest_bilingual_candidates()`）是共现启发式，不是真正的术语对齐——只看"这个译文候选是否格外集中出现在含有该原文候选的句对里"，没有语序/语法信息，小语料（含某候选的句对不到几十条）通常给不出配对，这是预期结果，不是 bug。
  - 没有 CJK 分词器/词典/词性标注，未实现完整版新词发现算法（左右邻字熵）；输出噪音水平取决于语料和参数，不承诺精度。
  - `_drop_nested()` 的嵌套过滤是 O(n²)，`suggest_bilingual_candidates()` 按每个候选重新扫一遍语料，大语料 + 高 `--top-n` 有明显变慢的可能，未做性能优化。

  测试见 `tests/test_terms_extract.py`、`tests/test_tm_cli.py`。
- **TBX / MultiTerm XML 互通** ✅（2026-09）：`language_tools/terms/tbx.py`，接入 `glossary.read()`/`glossary.write()` 的 `.tbx` 扩展名分发，`term-check`/`term-extract-promote` 等所有走 `--glossary` 参数的命令自动获得 TBX 支持，没有新增 CLI 子命令。落地过程证实了"风险"栏的两条判断都是真的，没有一条是过度谨慎：
  - **方言问题是真的**：TBX 2008/TBX-Basic（`termEntry`/`langSet`/`tig`，MultiTerm/Trados/多数现存 TBX 文件实际用的）和 ISO 30042:2019"TBX 3.0"（改名成 `conceptEntry`/`langSec`/`termSec`，外加一个默认命名空间）是两套不兼容的元素命名。`read()` 按本地标签名兼容两种；`write()` 只输出前者，因为 DESIGN.md 这条本身点名的目标工具（Trados/MultiTerm）用的就是前者。
  - **MultiTerm 私有字段混用问题也是真的**：真实 MultiTerm 导出里的自定义 `descripGrp`/`descrip` 字段、多同义词 `tig`（一个概念下多个同语言候选词）在我们的 `TermEntry`（一行一个 src/tgt 词对，只有 approved/forbidden 两态）里根本没有对应位置。没有强行塞、也没有静默丢弃后假装完整——`read()` 只读 `<term>`、`administrativeStatus`、首个 `<note>`、`<descrip type="subjectField"|"domain"|"category">` 这几个有明确映射的字段，其余一律忽略；同义词只保留每语言下第一个 `<tig>`/`<termSec>`，多余的计数并打印警告，不猜哪个源语言同义词该配哪个目标语言同义词。
  - `administrativeStatus` 官方 picklist（`preferredTerm-admn-sts`/`admittedTerm-admn-sts`/`deprecatedTerm-admn-sts`/`supersededTerm-admn-sts`……）和 Weblate 等工具实际在用的简写值（`forbidden`/`deprecated`）都识别，统一折叠进我们的二态模型；`write()` 用官方 picklist 值（`forbidden`→`deprecatedTerm-admn-sts`，已声明的 `approved`→`preferredTerm-admn-sts`，未声明的 fallback `approved` 不写 termNote，避免把一个从没真正设置过状态的词条写成"官方推荐术语"）。
  - **"往返保真"的承诺范围写清楚了，没有夸大**：只保证"本模块自己写出来的文件，读回来是原样的"，不承诺能完整复现第三方 MultiTerm 导出——上面两条会丢的东西，丢了就是丢了。

  测试见 `tests/test_terms_tbx.py`（含跨方言读取、官方/简写状态值映射、同义词丢弃警告、命名空间处理）、`tests/test_terms_glossary.py`（`.tbx` 分发不影响既有 csv/xlsx 路径）、`tests/test_tm_cli.py`（`term-check`/`term-extract-promote` 端到端接受 `.tbx`）。

至此，DESIGN.md 15.2 第一优先批次四项全部落地（字数估算/报价器、术语提取、fuzzy 近重复检测、TBX/MultiTerm 互通），两处已知的 GUI 缺口也已补上（见下）。
- **Fuzzy 近重复检测** ✅（2026-09）：`language_tools/tm/near_dup.py` + `tmtool near-dup`。落地时把"编辑距离或 minhash"里选了前者——`difflib` 编辑距离比值（复用 `tm.leverage` 同一套指标和归一化，保持"相似度"在全代码库里是同一个口径），配一个基于长度的剪枝：由 `ratio = 2M/(len_a+len_b)` 且 `M<=min(len_a,len_b)` 这个定义本身可以推出一个精确的长度比上界，凡是长度差超出这个上界的候选对，数学上不可能达到阈值，剪掉它们不会漏掉任何真正满足阈值的候选对——不是 minhash/LSH 那种近似分桶，牺牲的是 minhash 在超大语料上的渐近性能优势，换来剪枝这一步本身零误差；真到生产级超大 TM 顶不住了，minhash/LSH 是文档里写明的升级路径，不需要推倒重来。**一个诚实的附注**：`difflib.SequenceMatcher` 本身在等长最长公共子串出现平局时，比值会随传参顺序有极小概率不对称（Python 标准库这个工具本来就有的性质，`tm.leverage` 用同一个指标时也没处理这个），`near_dup.py` 固定"短文本在前"的比较顺序，没有为了消除这个边界情形去比较两种顺序取较大值——影响面窄到只有卡在阈值边缘的极少数候选对，不值得为此翻倍比较开销。聚类按连通分量合并（A~B、B~C 但 A~C 不一定成立时，三者仍会被分进同一簇），docstring 里说明了这是标准做法而非 bug。测试见 `tests/test_tm_near_dup.py`（含一次基于随机语料、与暴力枚举比对的剪枝精确性回归测试）、`tests/test_tm_cli.py`。GUI 侧"配合【TM 编辑】页逐簇裁决"✅（2026-09）：【TM 编辑】页新增"查找近重复…"对话框（`toolbox/tools/tm_editor/page.py` 的 `_NearDupDialog`），阈值/比较原文或译文/最小簇大小可调，结果表格每簇一组互斥"留"复选框（用普通可勾选 `QTableWidgetItem` 手写互斥逻辑，不用 `setCellWidget`，理由同术语提取候选表），默认留每簇第一条，"应用"后从当前记忆库里删掉每簇里没被选中的记录、标记未保存。同步运行，没有走 worker 线程——这个量级的相似度分簇不至于卡住交互，真要是在特别大的记忆库上跑慢了，那时候再加 worker，不是现在预先付这个复杂度的代价。测试见 `tests/test_toolbox_tm_editor_page.py`。

术语提取候选审核 GUI ✅（2026-09）：【术语管理】页新增"候选词提取"tab（`toolbox/tools/term_management/page.py`），刻意比 CLI 简化了两处，都在 `_build_extract_tab()` 的 docstring 里写明白了原因：输入只接受 tmx/sdltm 语料文件，不支持 `tmtool term-extract` 那一整套双语源文件读取选项（版式/表头/分隔符……）；没有走"导出候选 CSV → 人工编辑 → 再导入提升"这条 CLI 路径，候选结果表本身就是审核界面（可编辑译文建议/领域/备注 + 勾选框），"提升到术语库"直接追加进这个页面正在编辑的术语库内存对象，因为这个页面本来就有打开-编辑-保存的完整流程，没必要为审核这一步多绕一层文件。提升后状态固定是"推荐译法"（已声明），不提供禁用译法选项——候选词提取产出的是"值得推荐的术语候选"，不是"值得禁用的错误译法"，这两者的判断依据完全不同，硬塞一个下拉框不代表真的有能力做出那个判断。测试见 `tests/test_toolbox_term_management_page.py`。这两个 tab/dialog 加完之后，`_GLOSSARY_OPEN_FILTER`/`_GLOSSARY_SAVE_FILTER` 顺手补上了 `.tbx`——TBX 那一轮只顾着改 `glossary.py` 的分发逻辑，漏了 GUI 文件对话框的过滤器，属于那次改动本该覆盖但没覆盖到的地方，不是这轮新加的范围。

**第二优先（低成本增强，复用 `reports/render.py` 或现有 `stats`/QA 基础设施）**：

- **双语对照审阅文档导出** ✅（2026-09）：`reports/adapters.py` 新增 `from_bilingual_review()`，只列有问题的段（`csv_writer` 的全量 CSV 导出已经覆盖"导出全部条目"，这里刻意不重复），原文/译文里触发高亮检查的具体字符标红——复用 `qa.SPAN_FINDERS`/新增的 `qa.merged_highlight_spans()`，和 QA 检查页结果表用的是同一套选片/合并逻辑（该函数原本是 `toolbox/tools/qa_check/page.py` 里的私有实现，这次提到 `qa.py` 成为两边共用的唯一实现，避免各自维护一份容易失步）。这是对 `render.py` 自己"不做逐条数据倾泻"原则的一次刻意例外：本模块其余报告都是全库统计摘要，唯独这个就是要给人逐行核对原文译文，天然是逐条的——`ReportTable` 因此加了 `raw_html` 字段（受信任的预转义 HTML 单元格，而不是被 `render_html()` 二次转义成看不出标红效果的纯文本），并设了 500 条行数上限（超出会在 summary_lines 里提示，不静默丢弃）。只支持 HTML：`write_pdf()` 遇到 `raw_html` 表格直接抛错，reportlab 单元格看不懂 HTML 标记，DESIGN.md 原本要的就是"HTML 页"，没有强行拼一个半成品 PDF。CLI 侧 `tmtool qa --review PATH`，GUI 侧【QA 检查】页新增"导出审阅文档…"按钮，和已有"导出报告…"走同一个 `report_render`/`report_adapters` 管线，同步执行（有行数上限兜底，不值得上后台线程）。测试见 `tests/test_reports_adapters.py`、`tests/test_reports_render.py`、`tests/test_tm_cli.py`、`tests/test_toolbox_qa_check_page.py`。
- **批量预检（preflight）** ✅（2026-09）：`language_tools/readers/docx_preflight.py`，`check(path, src_lang=None, tgt_lang=None)` 四项检查全部复用现有基础设施，不重新发明——版式置信度直接调用 `docx_table`/`docx_numbered`/`docx_alternating` 三个 reader 各自已有的 `confidence()`（和 `readers/docx.py` 自动识别选版式用的是同一套分数，低于 0.85——每个 reader 自己 docstring 里"强信号"那一档的门槛——就算置信度偏低，提示手动 `--layout` 确认）；合并单元格/空表格新增 `_ooxml.iter_body_tables_with_merge_flags()`（读 `<w:tcPr>` 里的 `gridSpan`/`vMerge`，`iter_body_tables()` 原样保留没动，怕改了返回形状连累 `docx_table.py` 现有调用方）；语言方向异常复用 `align/splitters.py` 的 `is_cjk_lang()`/`looks_cjk()`——这俩函数在这个项目里已经在 `pick_splitter()` 里做过一次一模一样的"声明语言 vs 内容嗅探"判断（DESIGN.md Phase 0 提过的"正向/反向语言方向"真实踩过的坑），预检只是把同一个判断挪到转换之前而已，不是新发明的逻辑；配套给 `docx_table.py` 加了 `sample_column_text()`（复用 `_qualifying_tables()`/`pick_src_tgt_columns()` 选列逻辑，不是另起一套）。`check()` 本身不判断通过/不通过，只把信号列出来，交给调用方（CLI 退出码、GUI 行颜色）决定。CLI 侧 `tmtool preflight FILE [--src] [--tgt] [--fail-on-issues]`（单文件，和 `align` 一样靠 `--fail-on-issues` 支持 shell 循环批量脚本化）；GUI 侧新工具页【批量预检】（`toolbox/tools/batch_preflight/`），结构照抄 `batch_alignment_check`（多选文件/文件夹→逐文件跑 `check()`→表格逐行报告，同一套 `QThread` worker 模式），只是仅接受 `.docx`、没有版式下拉框（预检本来就是要把三种版式的置信度都摆出来看，不是先选好一种）、状态只分两色（绿=未发现问题，红=有问题或预检失败，靠文字前缀区分），问题详情放在结果格的 tooltip 里。测试见 `tests/test_docx_preflight.py`、`tests/test_docx_table_reader.py`（新增 `sample_column_text()`/合并单元格探测用例）、`tests/test_tm_cli.py`、`tests/test_toolbox_batch_preflight_page.py`；新增两个 fixture（`table_merged_header.docx`、`table_with_empty_table.docx`，`python-docx` 一次性生成，不是运行时依赖）。
- **语料资产盘点增强** ✅（2026-09）：`language_tools/tm/stats.py` 的 `compute()` 加了 `aging`（按 `modified_at` 年份分桶，含 `unknown` 桶）和 `lang_pair_by_domain`（语言对 × 领域交叉表）两个字段。"领域"这次没有硬造：`TranslationUnit` 上根本没有 `domain` 字段（只有 `terms` 那边的 `TermEntry` 有），TMX/SDLTM 两个 reader 现在也都不解析任何领域类信息（TMX `<prop>` 完全没读，SDLTM 的 `fields`/`context_groups` 表也没碰）——真要把"领域"这个概念从零建起来是新的 reader 能力，不是"低成本增强"。所以做法是：优先读 `meta['domain']`（`model.py` 自己说明的"暂未跨格式通用信息"逃生舱口，以后不管手动打标还是自动化步骤往这里塞数据都直接生效），没有就退到每条记录的 `source_file` 文件名——这不是瞎凑合，`merge.py` 合并多个来源 TMX/SDLTM 时压根不碰每条记录自带的 `source_file`，现实里"多个项目 TM 合并成一个语料库"这种场景，文件边界本来就基本约等于项目/领域边界。但这也意味着这个代理指标只在"合并后不落盘直接读"这条路径上才有意义——TMX/SDLTM 都不会在保存时把"这条记录原本来自哪个文件"这种血统信息写进去，`tmtool stats` 原本的单文件参数因此顺手改成了 `inputs`（`nargs='+'`，和 `compare` 子命令一个路数，读入后直接拼起来算总账、不去重，要去重先跑 `merge`），不然这个交叉表在"先 merge 落盘、再 stats"这条最直觉的 CLI 用法下什么信息都留不住——这个限制在 `tm_cli.py` 的 `--help` 里和 `stats.py` 的模块 docstring 里都写明白了。CLI 侧顺手给 `stats` 也配了 `--report`（复用 `reports/render.py`，新增 `report_adapters.from_stats_summary()`，一张表用"类别"列区分总数/语言对/aging/交叉表四段，没有另起三张表），凑齐了 `leverage`/`compare`/`qa_check`/`stats` 四个有 `--report` 的子命令。GUI 侧【TM 维护】页"统计"tab 的结果表跟着加了对应行，并补了"导出报告…"按钮（复用 `leverage`/`compare` 两个 tab 已有的 `_start_export_report()`，不是另起一套）。测试见 `tests/test_tm_stats.py`、`tests/test_reports_adapters.py`、`tests/test_tm_cli.py`、`tests/test_toolbox_tm_maintenance_page.py`。
- **标点规范专项 QA** ✅（2026-09）：`language_tools/qa.py` 新增三项检查，走既有 `qa.run()` 管线——PUNCTUATION_UNBALANCED（括号/引号/书名号配对，覆盖 ASCII 括号、CJK 书名号《》『』方括号【】、智能引号“”‘’；直引号 `"`/`'` 故意不检，因为英文里同一个字形既当开也当关，`'` 还兼职撇号，"don't" 这种正常句子会被误判）、WIDTH_MIXING（同一段落里同一个标点的半角/全角同时出现，如 `!` 和 `！` 都在；逗号句号故意排除在外，两者是千分位/小数点/缩写里的常客，跟数字混在一起会撞上 NUMBER_MISMATCH 早就绕开过的那类假阳性）、LEADING_TRAILING_SPACE（原文/译文首尾空白，含容易被忽略的 CJK 全角空格 U+3000）。三项都是 count-based/单段自查，不是 src/tgt 语义比对，判定标准延续 TAG_MISMATCH"只比数量不比顺序"的克制原则。落地是纯粹的现有基础设施复用：`tm/qa_report.py` 的 `ISSUE_TYPES`、CLI `--type`、CSV 导出、报告 adapter、【QA 检查】页过滤下拉框和结果表都是通用遍历 `ISSUE_TYPES`/`ISSUE_LABELS`，加两个字典条目就自动接入，没有新增专门的接线代码。GUI 高亮延续"标红全部涉及字符，人工判断哪个是问题"的既有套路（`find_punctuation_pair_spans`/`find_width_mixing_spans`，与 `find_number_spans` 等同一思路）；LEADING_TRAILING_SPACE 不参与高亮——空白字符标红也看不见，没有意义。测试见 `tests/test_qa.py`。
- **导出 JSONL 训练格式** ✅（2026-09）：`language_tools/writers/jsonl_writer.py`，`csv_writer` 旁加的第四个 writer，纯本地格式转换，没有任何网络调用，不违反"不上传文件"定位。行为上更接近 tmx/sdltm 而不是 csv：`csv_writer` 刻意保留空 src/tgt 行方便人工审阅缺口，这里反过来——训练样本有一边是空的没有意义，静默跳过（与 tmx/sdltm 一致）。字段没有照抄任何一家训练框架的 chat schema（OpenAI/Alpaca/ShareGPT 的 `messages`/`instruction` 包装）：DESIGN.md 这条只要求"一种训练格式"，没指定具体框架，猜错了框架等于让下游再转一次；每行走的是扁平的 `src_lang`/`tgt_lang`/`src`/`tgt`，谁都能按自己训练脚本的需要再包一层。语言对没有像 tmx/sdltm 那样只写一次在文件头——JSONL 的典型用法是多次转换产出的文件直接拼接成一份训练语料，拼接之后单文件的头就没地方放了，所以语言对跟着每一行走。编码上特意不跟 `csv_writer` 走 `utf-8-sig`：这份文件的读者是 JSON 解析器/训练脚本，不是 Excel，BOM 反而会打断朴素的逐行 JSON 解析；`ensure_ascii=False` 保持中文可读。接入面：`biconvert --to jsonl`（`language_tools/cli.py`，新增 `_TO_CHOICES` 常量，特意与默认格式包 `_ALL_FORMATS` 分开——jsonl 是训练数据导出，不该因为选项存在就默认跟着 sdltm/tmx/csv 一起生成，必须显式 `--to jsonl` 或 `-o out.jsonl` 才会写出）；`api.convert()` 的 `formats` 参数同理，默认值原样保留 `('sdltm', 'tmx', 'csv')` 不变。GUI 侧【语料转换】和【批量转换】两个页面的"生成格式"区都加了 jsonl 复选框，默认不勾选（跟其余三个默认勾选相反，理由同上），勾选状态走既有的 `_fmt_manual_state`/settings 持久化机制。测试见 `tests/test_writers_jsonl.py`、`tests/test_cli.py`、`tests/test_toolbox_corpus_convert_page.py`、`tests/test_toolbox_batch_convert_page.py`。

至此，DESIGN.md 15.2 第二优先（低成本增强）批次五项全部落地（双语对照审阅文档导出、批量预检、语料资产盘点增强、标点规范专项 QA、导出 JSONL 训练格式）。

**第三优先（战略性，需要单独权衡工作量或产品定位）**：

- XLIFF 1.2/2.0 读写：能打通"译前准备/译后回收"整段工作流的真正 CAT 交换标准，但方言多、工程量大，需要单独立 Phase，不适合顺手做
- SRX 断句规则导入导出：分句算法是现有核心竞争力之一，开放给高级用户自定义有价值，但要先确认不会削弱现有 `pick_splitter` 的可维护性
- LLM 语义 QA：能抓"漏译半句""术语对但语义不对"这类规则 QA 抓不住的问题，但直接冲突 README 的"不联网、不上传文件"承诺——**如果做，必须是显式 opt-in 的可选外挂**（架构上预留 reviewer 接口，本地小模型或用户自备 API key），不能进默认流程，也不能悄悄改变工具箱"纯离线"的定位
