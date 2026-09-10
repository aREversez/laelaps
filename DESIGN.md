# bi-corpus-tools 开发方案（v1，供 opencode 实现）

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
- 仓库：`aREversez/language-tools`。GUI 工具箱和核心库同仓库，不拆独立仓库（见第13节）。
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
    │   └── page.py            # 文件/语言/版式（复用 corpus_convert 的 widgets）+ 结果表格 + 筛选 + 导出 CSV
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
