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
transcribe the supporting screenshot into a text evidence file under
`compatibility/fixtures/` (raw screenshots are **not committed** — this repo
is public and full-window shots are direct evidence of a licensed-app
install on a personal machine; see `fixtures/README.md`), and open an
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
| `large_unique.sdltm`                             | Hand-built via API, 1000 unique TUs | Round-2 addition: same size as `large` but zero duplicates — isolates the duplicate-segment suspect for the FGA upgrade failure |

## Status summary

| Fixture             | Last verified | Studio version | biconvert commit | Status    |
|---------------------|---------------|----------------|-------------------|-----------|
| `basic.sdltm`        | 2026-09-22    | Studio 2024 (build 18.0.2.3255) | `a6580b3` | PASS-WITH-CAVEATS |
| `special_chars.sdltm` | 2026-09-24   | Studio 2024 (build 18.0.2.3255) | `a6580b3` | PASS-WITH-CAVEATS |
| `numbering_mismatch.sdltm` | 2026-09-22 | Studio 2024 (build 18.0.2.3255) | `a6580b3` | PASS-WITH-CAVEATS |
| `large.sdltm`        | 2026-09-24    | Studio 2024 (build 18.0.2.3255) | `a6580b3` | PASS-WITH-CAVEATS |
| `reversed.sdltm`    | 2026-09-22    | Studio 2024 (build 18.0.2.3255) | `a6580b3` | PASS-WITH-CAVEATS |
| `large_unique.sdltm` | 2026-09-24   | Studio 2024 (build 18.0.2.3255) | `a6580b3` | FAIL (upgrade at 1000 TUs) |

Replace `UNKNOWN` with `PASS` / `FAIL` / `PASS-WITH-CAVEATS` as entries are
added below. A `FAIL` row should link to an issue and to a verification
entry with the failure details.

---

## Known issue: "upgrade available" loop with no error and no progress

> **Status update 2026-09-22: hypothesis DISPROVED, real cause identified.**
> Kept below for the record; see the corrected analysis further down in this
> section.

Symptom reported 2026-09-08: Studio's Translation Results window shows the
standard "An upgrade is available for your translation memory..." prompt for
a `.sdltm` produced by this writer. Clicking **Upgrade** returns immediately,
shows no error, but the TM is still flagged as needing upgrade afterward
(non-upgraded warning-triangle icon persists).

Leading hypothesis (not yet confirmed against a real Studio install — see
caveat below): this prompt is Studio's **upLIFT fragment-alignment upgrade**
(introduced Studio 2017), which builds a statistical translation model from
the TM's segments. Published SDL/RWS guidance states the TM needs **at least
1,000 segments (5,000 recommended)** for the model-build step to run; TMs
below that threshold appear to let the upgrade silently no-op — no error
dialog, but the non-upgraded flag never clears. All fixtures verified so far
were small (`basic.sdltm` ~3-4 TUs, `numbering_mismatch.sdltm` ~dozens), which
would explain the symptom without indicating an actual schema defect in
`sdltm_writer.py` (Level 1 SQLite-schema tests still pass; nothing in the DDL
or row data looks wrong for this).

**Action for next verification round**: retest with `large.sdltm` (the
1000+-TU fixture already called for in the test matrix above) instead of a
small fixture, and record whether the upgrade completes. If it still loops
at 1000+ TUs, the hypothesis is wrong and the real cause needs fresh
empirical investigation (check Studio's log file under
`%APPDATA%\SDL\SDL Trados Studio\...\logs`, check file isn't on a
cloud-synced/read-only path, check TM isn't open in another process).

### Retest result 2026-09-22 (Trados Studio 2024, build 18.0.2.3255): hypothesis wrong

Tested with `large.sdltm` (1000 TUs, local non-synced `%TEMP%` path).
The upgrade prompt **still loops at 1000+ TUs**, and this time Studio did
surface a real error, in the upgrade log
(`fixtures/TranslationMemoryUpgrade-20260922-210041.log`):

```
Upgrade Translation Memory
Translation memory: ...\large.sdltm
Process failed
Sdl.LanguagePlatform.Core.LanguagePlatformException: The TM does not support FGA
   at ...AbstractLocalTranslationMemory.Save(...)
```

So the "< 1,000 segments threshold" theory is **out**. Corrected
understanding from this round:

1. **The prompt is not a size issue at all.** The trigger is the
   *absence* of the FGA structures — above all the
   `translation_memories.fga_support` column, which only exists after a
   successful upgrade. (`sdltm_writer` emits `parameters.VERSION =
   '8.06'`; the 2026-09-23 schema research below showed Studio keeps
   `VERSION='8.06'` even in a fully upgraded TM, so VERSION is **not**
   the trigger — an early guess in this section, corrected.) Every TM we
   write is therefore flagged as needing the upLIFT/FGA upgrade,
   regardless of TU count. The prompt appearing is expected behavior for
   our Level 2 claim; the loop is what's not.
2. **"Silent no-op" was actually a silent-in-UI failure.** The upgrade
   wizard's progress dialog can stay "in progress" indefinitely (12+ min
   observed, zero CPU) even though the background job already failed
   within the same second — check the upgrade log, not the dialog. That
   mismatch is what made the failure look like a no-where-to-be-found
   no-op.
3. **Un-upgraded TUs can't be edited back.** Open/Browse/Search all pass
   on un-upgraded files, but Edit→Commit fails with
   `no such table: translation_unit_fragments` — the writer's DDL has no
   FGA fragment table, which is exactly what Studio writes edited TUs to.
   After a successful upgrade (done on `basic.sdltm` as a control), the
   fragments table is built and Edit→Commit passes.
4. **Open puzzle for the next round: upgrade succeeds on `basic` but
   fails on `large`.** Control experiment: `basic.sdltm` (4 unique TUs)
   upgraded cleanly end-to-end
   (`fixtures/TranslationMemoryUpgrade-20260922-215932.log`), while
   `large.sdltm` died with "does not support FGA". Both came from the
   same writer. Leading new suspect: `large`'s 250× exact-duplicate
   segments (it also throws `TMTUDuplicate` on commit), but this is not
   yet confirmed — candidates to rule it in/out: dedupe `large` and
   retest, and test `special_chars` (2 unique TUs, hand-built like
   `large`) *with* Upgrade clicked.

Level 2 claim remains defensible with the caveat: **Studio can open,
browse and search everything we write; edit-after-upgrade works at least
for non-duplicate TMs; the upgrade itself fails on `large.sdltm`** —
tracked below until root-caused.

### Offline schema research 2026-09-23 — what Studio's upgrade actually does

No Studio interaction needed: the round-1 control experiment left us a
Studio-**upgraded** copy of `basic.sdltm` on the test machine. Diffing it
against the pristine writer output gives the authoritative answer for
free. A Studio 2024 FGA upgrade:

- **adds 4 columns to `translation_memories`**: `fga_support` (=1),
  `data_version` (=1), `text_context_match_type` (=1),
  `id_context_match` (=0) — `fga_support` is what the
  "The TM does not support FGA" exception checks;
- **adds 9 columns to `translation_units`**: `source_token_data`,
  `target_token_data`, `alignment_data`, `align_model_date`,
  `insert_date`, `tokenization_sig_hash`, `source_tags`, `target_tags`,
  `fragment_hash`;
- **adds 7 tables**: `translation_unit_fragments`
  (`translation_unit_id INT FK→translation_units ON DELETE CASCADE,
  fragment_hash INTEGER NOT NULL` + indexes on both columns),
  `translation_unit_idcontexts`, `trans_model`, `trans_model_rev`,
  `vocab_src`, `vocab_trg`, `vocabfilter`;
- **adds 3 `parameters` rows** (with `translation_memory_id` NULL):
  `TokenDataVersion=1`, `AlignmentDataVersion=1`, `VERSION_CREATED=8.12`;
- **leaves `VERSION` at `8.06`** and leaves the existing 13 tables and
  TU data untouched (pure additive `ALTER TABLE`/`CREATE TABLE`).

Notably the upgraded 4-TU `basic` had **all 7 new tables empty** —
consistent with the published "model needs ≥1,000/5,000 segments"
guidance being about *content*, while the upgrade itself is structural.
If Studio accepts "structures present but empty" as upgraded (round-2
probe: reopen the upgraded basic copy, expect *no* prompt), then the
writer fix is purely additive DDL — emit the post-upgrade schema and the
prompt/edit gaps disappear together. The pinned baseline tests in
`tests/test_sdltm_schema_baseline.py` guard that any such change is
deliberate.

### Round-2 plan (2026-09-23)

Method correction from round 1: after clicking Upgrade, **do not watch
the wizard UI** (it can hang 12+ min after the job already finished);
wait ~90 s and read the newest `TranslationMemoryUpgrade-*.log` in the
working folder instead.

1. **Upgraded-basic probe** — reopen the round-1 upgraded
   `basic.sdltm` copy: expect *no* upgrade prompt, and Edit→Commit to
   work. Confirms "empty FGA structures satisfy Studio".
2. **special_chars + Upgrade** — click Yes this time; then Edit→Commit.
   If it upgrades cleanly, the hand-built API path is exonerated and the
   `large` failure narrows to content (duplicates).
3. **`large_unique.sdltm` (new fixture, deduped 1000 TUs) + Upgrade** —
   the duplicate-segment suspect, tested directly.
4. **`large.sdltm` upgrade retest** — confirm the failure is
   reproducible and not a round-1 fluke (e.g. file lock from its own
   open editor tab).

Outcome decision table: if 3 passes and 4 fails → duplicates are the
cause, fix = dedupe guidance + writer-side duplicate handling; if 2
passes and 3 fails → size is the cause after all; if 4 passes this time
→ round-1 failure was environmental, chase the lock instead.

### Round-2 final results (2026-09-24) — root cause identified

**Neither branch of the decision table won outright — the real rule is
narrower than any candidate, and the duplicate-segment suspect is dead.**

| Test | Result | Key evidence |
|------|--------|--------------|
| 1 upgraded-basic reopen | PASS | No prompt, edit commits work → "structures present but empty" counts as fully upgraded; writer fix is purely additive DDL |
| 2 special_chars + upgrade | PASS | 3-step wizard, `fga_support` → 1; then Edit→Commit persisted (round-1's `translation_unit_fragments` failure gone) |
| 3 large_unique + upgrade | **FAIL** | 5-step wizard (adds Build Translation Model + Align TUs); dies at Upgrade step with `The TM does not support FGA`; leaves `fga_support=3` + empty structures → subsequent commits **fail silently** (no dialog, `Last modified` unchanged) |
| 4 large retest | PASS (this time) | 3-step wizard, `fga_support` → 1, Reindex logs **999** TUs |

The smoking gun: **`large` failed round 1 at exactly 1000 TUs and succeeded
round 2 at 999** — it lost one TU to round 1's edit/`TMTUDuplicate`
churn, accidentally crossing the threshold. Combined with test 3 (1000
*unique* segments still fails) the rule is:

> **Upgrade TMs with < 1,000 TUs succeed (3-step wizard). At ≥ 1,000 TUs
> Studio adds the "Build Translation Model"/"Align Translation Units"
> steps, and that step throws `LanguagePlatformException: The TM does not
> support FGA` on `AbstractLocalTranslationMemory.Save` against any
> writer-produced file — duplicate content irrelevant.**

So the original published "needs ≥1,000 segments for the model build"
guidance was directionally right, but inverted in effect: the prompt
loop is *caused by* the model-build step being attempted, not by the TM
being too small to bother. Why the model-build Save rejects our files is
the next open question (candidates: missing per-TU tokenization data,
`attributes`/`settings` contents, TU `flags` value).

**Proposed fix (round-3 validation pending)**: writer emits the full
post-upgrade schema — 4 extra `translation_memories` columns with
`fga_support=1`, 9 extra `translation_units` columns, the 7 FGA tables,
3 extra `parameters` rows (exact diff in the schema research above) — so
Studio never offers the upgrade at all. Validation probe: flip
`large_unique`'s `fga_support` 3→1 in raw SQLite, reopen in Studio;
expect no prompt and working commits. If Studio instead re-derives
something at open, the writer fix needs the model-build precondition
found first.

Also from this round: for already-registered TMs, double-click does not
re-trigger the upgrade prompt — only first-open via File → Open
Translation Memory does (used for all three round-2 upgrades; the
"Batch Tasks → Update Translation Memories" path was not reachable in
this Studio's TM-view ribbon/context menus).

### Round-2 partial results (paused 2026-09-23, tests 2–4 not yet run)

- **Test 1 PASS — the upgraded-basic probe confirms the fix direction**:
  reopening the round-1 upgraded `basic.sdltm` (450 KB, `fga_support=1`,
  all 7 FGA tables present but **empty**) shows **no upgrade prompt**,
  and its Edit→Commit was already verified working. So Studio accepts
  "structures present, contents empty" as fully upgraded → the writer
  fix really is purely additive DDL (see schema research above).
- **Trigger-condition discovery**: double-clicking a TM already
  registered in the TM tree does **not** raise the upgrade prompt; only
  first open via File → Open Translation Memory does. Next session,
  trigger upgrades deterministically via **Batch Tasks → Update
  Translation Memories** (or open never-registered files through the
  Open dialog).
- Remaining: test 2 (special_chars + upgrade → Edit), test 3
  (`large_unique` + upgrade, search `Record 0500`, Edit), test 4 (`large`
  upgrade retest). Fixture files and `large_unique.sdltm` are already in
  the working folder; success/failure is judged from the newest
  `TranslationMemoryUpgrade-*.log`, not the wizard UI.
- Housekeeping for future evidence rounds: the upgraded fixture's
  `translation_units.change_user` recorded `MACHINE\username` (Studio
  stamps the Windows identity on commit). The .sdltm files are not
  committed, but any DB field dumps pasted into this ledger must be
  scrubbed first.

This is exactly the kind of Level-2 claim that can't be settled from the
sandbox — it needs a real Studio install and should get its own
`### large.sdltm` verification entry below once tested, per the template.
→ done 2026-09-22, see Verification entries.

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

Round 2026-09-22 — first verification round on a real install (Trados
Studio 2024, build 18.0.2.3255). All five fixtures generated per
`compatibility/fixtures/README.md` at commit `a6580b3` and copied to a
local non-synced `%TEMP%` folder before opening. Screenshot contents are
transcribed verbatim in
[`fixtures/evidence-2026-09-22.md`](fixtures/evidence-2026-09-22.md)
(`evidence §n` references below); the upgrade logs are committed there
with local paths normalized to `<TESTDIR>`.

### basic.sdltm

- Studio version: Trados Studio 2024 (build 18.0.2.3255)
- biconvert commit: `a6580b3`
- TU count exported: 4
- Open: OK — no error dialogs
- Browse: OK — 4 TUs listed, CJK targets clean
- Search: OK — phrase taken from first listed TU, ≥1 hit, targets clean
- Edit: OK **only after clicking Upgrade** — the upgrade wizard completed
  cleanly (Backup → Upgrade → Reindex, `Process completed` in
  `TranslationMemoryUpgrade-20260922-215932.log`), which created the
  missing `translation_unit_fragments` table; then change-one-char +
  commit succeeded (evidence §6)
- Notes: control case for the upgrade-loop investigation — proves the
  upgrade path itself *can* succeed against our writer output at small
  TU counts. This copy of the fixture was mutated by the upgrade; the
  un-upgraded `tests/temp/basic.sdltm` is intact.

### special_chars.sdltm

- Studio version: Trados Studio 2024 (build 18.0.2.3255)
- biconvert commit: `a6580b3` (hand-built via API per fixtures README)
- TU count exported: 2
- Open: OK
- Browse: OK — **`esc()` verification passed verbatim**: TU1 src shows
  literally `The spec says R&D output &lt; 5% error, use < and >.`
  (`&lt;` neither decoded nor double-escaped to `&amp;lt;`); TU2 tgt
  shows `销售额增长了，例如第三季度<翻倍>并且&三倍。` with `<`, `>`, `&`
  intact (evidence §4)
- Search: OK — `R&D` → 1 hit, special chars render correctly in results
- Edit: **FAIL without upgrade** — commit threw
  `SQLiteException: no such table: translation_unit_fragments` at
  `UpdateTuAlignmentDataAsync` (evidence §3)
- Notes: upgrade prompt appeared but **No** was clicked deliberately, to
  keep this as the un-upgraded esc-correctness case. Retest *with*
  Upgrade clicked to help isolate the `large` upgrade failure.
  **Round 2 (2026-09-24): upgraded cleanly (3-step wizard,
  `fga_support` → 1), then Edit→Commit persisted with no error — hand-built
  API path exonerated; the fragments-table failure is purely a consequence
  of the un-upgraded state, not of `esc()` or the API route.**

### numbering_mismatch.sdltm

- Studio version: Trados Studio 2024 (build 18.0.2.3255)
- biconvert commit: `a6580b3`
- TU count exported: 2
- Open: OK
- Browse: OK — 2 TUs (`First sentence.→第一句。`, `Second sentence.→第二句。`)
- Search: OK — `First sentence` → 1 hit
- Edit: FAIL without upgrade — same `translation_unit_fragments`-family
  commit failure, surfaced as "The translation memory or TM container
  appears to be missing and may have been deleted."
  (evidence §2)
- Notes: actual alignment output is 2 TUs, not the "dozens" the test
  matrix table once guessed — the fixture doc itself only yields 2
  aligned pairs.

### large.sdltm

- Studio version: Trados Studio 2024 (build 18.0.2.3255)
- biconvert commit: `a6580b3`
- TU count exported: 1000
- Open: OK — no "unsupported/corrupted" dialog; first-open TU grid
  paginated 50/page × 20 pages
- Browse: OK — Studio reports 1000 TUs; CJK targets clean
  (evidence §5); System Fields show Created by=laelaps
- Search: OK — `Dr. Smith arrived` → ~250 hits across pages, targets
  clean → fuzzy index builds fine from an empty `fuzzy_data` table
- Edit: works on-screen, but committing an edit to one of the 250×
  duplicate segments threw `Translation Unit ID: 1, Error Code:
  TMTUDuplicate` (evidence §1)
- Notes: **the upgrade fails** — "An upgrade is available" → Upgrade →
  Backup ok → Upgrade step dies in <1s with
  `LanguagePlatformException: The TM does not support FGA`
  (`TranslationMemoryUpgrade-20260922-210041.log`) while the wizard's
  progress dialog hangs "in progress" 12+ min. This disproves the
  <1,000-segment threshold hypothesis for the upgrade loop (see Known
  issue above). Duplicate-segment content is the leading new suspect.
  → **Round 2 (2026-09-24): upgrade SUCCEEDED — at 999 TUs** (one TU lost
  to round 1's edit/`TMTUDuplicate` churn), 3-step wizard, `fga_support`
  → 1, Reindex logs 999. Combined with `large_unique` failing at 1000
  *unique* TUs, the real rule is the ≥1,000 model-build step, not
  duplicates — see Round-2 final results above. This file's on-disk state
  is now upgraded and 999 TUs; the pristine 1000-TU original regenerates
  from the fixtures README recipe.

### large_unique.sdltm

- Studio version: Trados Studio 2024 (build 18.0.2.3255)
- biconvert commit: `a6580b3` (hand-built via API, 1000 **unique** TUs)
- TU count exported: 1000
- Open: OK
- Browse: OK — 1000 TUs (page x of 20), CJK clean
- Search: OK — `Record 0500` → 1 hit via Source Text filter (note: the
  TM-maintenance view offers no Concordance mode; only "Search entire
  TM" / "potential duplicates")
- Edit: **FAIL — silent** — after the failed upgrade, commits produce no
  dialog, no `Last modified` refresh, nothing persists (worse
  diagnostics than round 1's explicit `translation_unit_fragments`
  error: an upgrade-failed TM swallows commits silently)
- Notes: **the disproving case** — upgrade dies at the 5-step wizard's
  Upgrade step with `The TM does not support FGA`
  (`TranslationMemoryUpgrade-20260924-201159.log`, paths sanitized),
  leaving `fga_support=3` + all 7 FGA tables created-but-empty on disk.
  Kills the duplicate-segment hypothesis; pins the failure to TU count
  ≥1,000 triggering Build Translation Model.

### reversed.sdltm

- Studio version: Trados Studio 2024 (build 18.0.2.3255)
- biconvert commit: `a6580b3`
- TU count exported: 2
- Open: OK — **language-code wiring confirmed**: TM tab shows
  `reversed [zh-CN->en-US]`, direction correct, no language errors
- Browse: OK — 2 TUs, zh as source / en as target, both clean
- Search: OK — `史密斯博士` → 1 hit, English target renders correctly
- Edit: FAIL without upgrade — same "TM container appears to be
  missing" commit failure (evidence §7)
- Notes: direction wiring (the point of this fixture) fully passes.
