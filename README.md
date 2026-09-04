# language-tools

双语文件 (docx/xlsx/csv) → 语料库格式 (sdltm/tmx) 转换库，以及语料库格式互转 (tmx↔sdltm)。

架构、阶段规划、已知限制见 [DESIGN.md](./DESIGN.md)。

## 当前状态：Phase 3（语料库互转）已完成

Phase 1（模块化重构）：
- `language_tools/model.py` — 核心 IR：`TranslationUnit` / `ParagraphPair`
- `language_tools/align/` — 分句器 + Gale-Church 式句级 DP 对齐算法
- `language_tools/readers/docx_numbered.py` — 编号版式双语 docx reader（`[1]..[N]` 源块 + `[1]..[N]` 译块）
- `language_tools/writers/` — sdltm / tmx / csv 写入器
- `language_tools/api.py` — 顶层 `convert()` 入口

Phase 2：
- `language_tools/readers/docx_table.py` — 表格版式双语 docx reader（2+ 列表格，一行一对）
- `language_tools/readers/docx.py` — docx 版式自动识别（表格优先，退回编号版式），支持 `layout=` 手动覆盖
- `language_tools/readers/xlsx_bilingual.py` — xlsx reader（依赖 openpyxl，理由见 DESIGN.md 7.1）
- `language_tools/readers/csv_bilingual.py` — csv/tsv reader，编码兜底 utf-8-sig→utf-8→gb18030
- `language_tools/readers/_rowreader.py` — 上述三个"行式" reader 共享的表头探测/列定位工具
- `language_tools/qa.py` — 轻量 QA 层（空值/长度比异常/重复TU/数字不匹配），`convert(..., qa=True)` 时启用

Phase 3（新增）：
- `language_tools/corpus_readers/tmx_reader.py` — TMX reader，直接产出 `TranslationUnit`（语料库文件已是句级，跳过对齐步骤）
- `language_tools/corpus_readers/sdltm_reader.py` — sdltm reader，解析 `translation_units` 表的 Segment XML
- `convert()` 现在同时支持双语源文件（docx/xlsx/csv/tsv，需要对齐）和语料库文件（tmx/sdltm，直接读取）两种输入路径，语料库输入的 `src_lang`/`tgt_lang` 可以从内容自动推断，不强制调用方提前知道

对照 Phase 0 回归基线（`tests/fixtures/`）验证：csv 输出与移植前的参考脚本逐字节一致；sdltm/tmx 输出语义等价（guid/时间戳除外，两者在写入时都是运行时生成的，见 DESIGN.md 第5节）。每个新 reader 都补了语言方向反转测试（DESIGN.md 6.4 强制要求）。tmx↔sdltm 互转补了往返测试，包括一个专门验证转义顺序的对抗性用例（文本里字面包含 `&lt;` 子串，用来暴露 esc/unesc 顺序颠倒会产生的错误结果——已用 kill-test 确认这个用例真的有区分力，不是摆设）。

移植过程中额外发现并修复了两个 bug：
1. `split_en` 对含内部句点的缩写（a.m./p.m./e.g./i.e./U.S./U.K./Ph.D.）的例外判断被一个多余且写反的正则条件抵消，导致这些缩写处被错误切句
2. QA 层的长度比检查最初用差值而非比值判定异常，导致"译文过短"这一侧的检测在数学上永远触发不了阈值（差值上限被 0 长度封顶在 1.0，而阈值设的是 1.5）——已用 kill-test 验证修复前后测试确实能区分

详见各模块 docstring 里的完整实测记录。

## 用法

```python
from language_tools import convert

convert("input.docx", "output_basename", src_lang="en-US", tgt_lang="zh-CN")
# 生成 output_basename.sdltm / .tmx / .csv
```

## 测试

```bash
pip install -e ".[dev]"
pytest tests/
```

## 尚未实现（后续 Phase，见 DESIGN.md）

- Phase 4：统一 CLI（`biconvert`）
- Phase 5（可选）：GUI
