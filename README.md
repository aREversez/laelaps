# language-tools

双语文件 (docx/xlsx/csv) → 语料库格式 (sdltm/tmx) 转换库，以及语料库格式互转 (tmx↔sdltm)。

架构、阶段规划、已知限制见 [DESIGN.md](./DESIGN.md)。

## 当前状态：Phase 1（模块化重构）已完成

- `language_tools/model.py` — 核心 IR：`TranslationUnit` / `ParagraphPair`
- `language_tools/align/` — 分句器 + Gale-Church 式句级 DP 对齐算法
- `language_tools/readers/docx_numbered.py` — 编号版式双语 docx reader（`[1]..[N]` 源块 + `[1]..[N]` 译块）
- `language_tools/writers/` — sdltm / tmx / csv 写入器
- `language_tools/api.py` — 顶层 `convert()` 入口

对照 Phase 0 回归基线（`tests/fixtures/`）验证：csv 输出与移植前的参考脚本逐字节一致；sdltm/tmx 输出语义等价（guid/时间戳除外，两者在写入时都是运行时生成的，见 DESIGN.md 第5节）。

移植过程中额外发现并修复了一个独立于此前已知语言方向 bug 的问题：`split_en` 对含内部句点的缩写（a.m./p.m./e.g./i.e./U.S./U.K./Ph.D.）的例外判断被一个多余且写反的正则条件抵消，导致这些缩写处被错误切句。详见 `language_tools/align/splitters.py` 模块 docstring 里的完整实测记录。

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

- Phase 2（下一步，已与用户确认优先级）：docx 表格版式、xlsx（openpyxl）、csv/tsv 双语源格式 reader，QA 层
- Phase 3：tmx/sdltm 语料库互转 reader
- Phase 4：统一 CLI（`biconvert`）
- Phase 5（可选）：GUI
