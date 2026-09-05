# language-tools

双语文件 (docx/xlsx/csv) → 语料库格式 (sdltm/tmx) 转换库，以及语料库格式互转 (tmx↔sdltm)。

架构、阶段规划、已知限制见 [DESIGN.md](./DESIGN.md)。

## 当前状态：Phase 4（统一 CLI）已完成

Phase 1（模块化重构）：
- `language_tools/model.py` — 核心 IR：`TranslationUnit` / `ParagraphPair`
- `language_tools/align/` — 分句器 + Gale-Church 式句级 DP 对齐算法
- `language_tools/readers/docx_numbered.py` — 编号版式双语 docx reader（`[1]..[N]` 源块 + `[1]..[N]` 译块）
- `language_tools/writers/` — sdltm / tmx / csv 写入器
- `language_tools/api.py` — 顶层 `convert()` 入口

Phase 2：
- `language_tools/readers/docx_table.py` — 表格版式双语 docx reader（2+ 列表格，一行一对）
- `language_tools/readers/docx.py` — docx 版式自动识别，支持 `layout=` 手动覆盖
- `language_tools/readers/xlsx_bilingual.py` — xlsx reader（依赖 openpyxl）
- `language_tools/readers/csv_bilingual.py` — csv/tsv reader，编码兜底 utf-8-sig→utf-8→gb18030
- `language_tools/qa.py` — 轻量 QA 层（空值/长度比异常/重复TU/数字不匹配）

Phase 3：
- `language_tools/corpus_readers/` — tmx / sdltm reader，支持语料库互转，`convert()` 可从语料库内容自动推断语言

Phase 4（新增）：
- `language_tools/cli.py` — `biconvert` 命令行工具，纯粹包装 `convert()` API（不含自己的业务逻辑，方便未来 GUI 复用同一套行为）
- `pyproject.toml` 注册了 `biconvert` 控制台入口，`pip install -e .` 后可直接使用
- 支持 `--to` 重复指定输出格式、`-o` 单格式简写（按扩展名推断）、默认输出名从输入文件名派生
- `--min-confidence` 阈值过滤（会隐式启用 QA）：低于阈值的 TU 不写入 sdltm/tmx，但 csv 永远列出全部内容（含被过滤的），csv 因此天然是一份"哪些被剔除、为什么"的审阅报告
- docx 新增第三种自动识别版式：**交替段落**（源段落、译段落交替出现），因为它没有任何正向识别信号（任意偶数段落的单语文档也"符合"这个形状），自动识别顺序里排在表格、编号版式之后，仅作为兜底

**顺带修复/增强（源于审阅第三方改写版 `docx_to_sdltm_v3.py` 时发现的问题）：**
- `aligner.MATCHES` 之前完全没有 `(1,0)`/`(0,1)` gap move：某个 `ParagraphPair` 一侧分句后变成空列表时，DP 无法到达终点，`_align_sentences` 会静默返回空列表——整段内容无声消失，没有任何警告。已修复；但注意 `GAP=60` 相对典型对齐代价（~2-6）大得多，所以这个 gap move 在实践中只有在"某一侧彻底为空"时才会被选中，并不会让算法倾向于把混在多个已译句子中间的单个未译句子识别成 gap（因为强行合并的代价仍然远低于 60）——这需要重新校准 GAP 常数，是一个更大的、需要单独决策的调整，本次未一并处理
- 每条 TU 现在在 `meta['alignment_cost']` 里暴露了 DP 对齐代价（本来就算出来了，之前直接丢弃），作为 QA 层之外的一个廉价补充诊断信号

对照 Phase 0 回归基线验证：以上改动均已确认对现有全部回归测试无影响；两处修复都用 kill-test 验证过（故意还原到修复前的代码，确认新测试真的会失败，不是摆设）。

详见各模块 docstring 里的完整实测记录。

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

## 测试

```bash
pip install -e ".[dev]"
pytest tests/
```

## 尚未实现（后续 Phase，见 DESIGN.md）

- Phase 5（可选）：GUI
