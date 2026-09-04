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

标签/占位符/URL 匹配这类检查先不做——现阶段的输入都是纯文本段落，还没有 inline tag 场景，等真正需要处理带标记的语料（比如以后支持 xliff）时再加，现在加是没有实际输入可测的空中楼阁。

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
- **Phase 5（可选）** — GUI，调用同一套 API

---

## 12. 交付与协作方式

- 走既定流程：opencode 在新仓库的 `dev` 分支实现，GitHub 作为同步媒介，Claude 后续负责审查 + 出 patch。
- 建议仓库名：`bi-corpus-tools`（或 Eliot 定）。
- 每个 Phase 建议拆成独立 PR/commit 序列，不要把 Phase 1 重构和 Phase 2 新功能混在一次提交里（符合"一次提交一个语义改动"的既有约定）。
- Phase 0 的基线必须先跑通、Phase 1 对照基线验证语义不变之后，再开始 Phase 2，避免在不稳定的地基上加新 reader。
