# SDLTM Studio-Readability Compatibility Ledger

This directory tracks the real-world status of `language_tools/writers/sdltm_writer.py`'s
**Level 2 — Studio-readable** compatibility claim (see DESIGN.md section 8).

Level 1 (SQLite schema) is covered by automated tests. Level 3 (Trados-private
fuzzy hashing) is explicitly out of scope. **Level 2 (Trados Studio can actually
open/browse/search/edit the .sdltm we produce) cannot be CI-tested** — it
requires a real Trados Studio install, which is a licensed, Windows-only, GUI
application. So we carry it as a manual verification ledger here.

## How to add a verification entry

Each fixture gets one section. The minimum information set is:

- **Studio version** — exact build number (Help → About in Trados Studio)
- **biconvert commit** — the git hash that produced the .sdltm being tested
- **TU count exported** — what `biconvert` reported on stdout
- **Open / Browse / Search / Edit** — one line per step (see below)
- **Notes** — anything notable (warnings, progress dialogs, anomalies)

The four steps each fixture must pass:

| Step   | Operation                                                | Failure mode                                            |
|--------|----------------------------------------------------------|--------------------------------------------------------|
| Open   | File → Open Translation Memory → pick the .sdltm         | "Unsupported" / "corrupted" / crash dialog             |
| Browse | Double-click the TM in the sidebar, view the TU list    | TU count mismatch; CJK mojibake; empty list            |
| Search | Concordance Search with a phrase from one of the inputs | 0 hits (fuzzy index not built); hit but garbled target  |
| Edit   | Right-click a TU → Edit → change one char → Save         | Save error; loss of other TUs; Studio crash on save    |

If a step fails, **don't hide it** — record the Studio error dialog verbatim,
attach a screenshot to `compatibility/fixtures/<fixture>.png`, and open an
issue referencing the commit that broke it. A "failed before, OK after"
entry is more valuable than a clean "OK" entry because it documents what
the writer was getting wrong and how it was fixed.

## Test matrix

Pick fixtures that exercise distinct code paths in `sdltm_writer`:

| Fixture name (under `compatibility/fixtures/`) | Source input               | Why it matters                                                                |
|------------------------------------------------|----------------------------|-------------------------------------------------------------------------------|
| `basic.sdltm`                                   | `tests/fixtures/docx/basic.docx`            | Smoke: 3-4 TUs, plain ASCII + CJK, no special chars                          |
| `special_chars.sdltm`                          | Hand-built via API           | Exercises `esc()`: src/tgt containing literal `<`, `>`, `&` and `R&D &lt;` |
| `numbering_mismatch.sdltm`                     | `tests/fixtures/docx/numbering_mismatch.docx` | Larger TU count, exercises non-trivial alignment output                     |
| `large.sdltm`                                   | Concatenated fixtures, ~1000+ TUs | Triggers Studio's first-open "updating indexes" progress dialog           |
| `reversed.sdltm`                                | `tests/fixtures/docx/reversed_direction.docx` | zh→en direction; tests language code wiring in `translation_memories` row |

## Status summary

| Fixture             | Last verified | Studio version | biconvert commit | Status    |
|---------------------|---------------|----------------|-------------------|-----------|
| `basic.sdltm`        | _(not yet)_   | —              | —                 | UNKNOWN   |
| `special_chars.sdltm` | _(not yet)_   | —              | —                 | UNKNOWN   |
| `numbering_mismatch.sdltm` | _(not yet)_ | —          | —                 | UNKNOWN   |
| `large.sdltm`        | _(not yet)_   | —              | —                 | UNKNOWN   |
| `reversed.sdltm`    | _(not yet)_   | —              | —                 | UNKNOWN   |

Replace `UNKNOWN` with `PASS` / `FAIL` / `PASS-WITH-CAVEATS` as entries are
added below. A `FAIL` row should link to an issue and to a verification
entry with the failure details.

---

## Verification entries

<!-- Template — copy and fill in:

### <fixture name>

- Studio version: Trados Studio <YEAR> <SR?> (build <NNNN.N.N.N>)
- biconvert commit: <hash>
- TU count exported: <N>
- Open: <result>
- Browse: <result>
- Search: <result>  <!-- include the search phrase used -->
- Edit: <result>
- Notes: <anything notable>

-->

_(no entries yet — see the instructions above to add the first one)_
