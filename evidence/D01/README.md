# D01 evidence — closing a past day deletes a tab that changed after the read

- Verified SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d` (base `eef98bb3`)
- Actor: `deepseek-durable-B`; queue-only checks, supported single-process path
- Environment: project `.venv`, Python 3.12.13, pytest 9.2.0, hash-pinned
  disposable runtime `scratch/runtime/app`
- Recorder receipt: `scratch/pipeline/D01/runs/f74001aa260d443481d4aa4a1d99dc48.json`
  (exit 1, no timeout, baseline clean after, test input hashed)
- Command:
  `.venv/bin/python scripts/review_pipeline.py run D01 --actor deepseek-durable-B --timeout 120 --artifact repro/D01/test_d01_snapshot.py -- .venv/bin/python scripts/run_review_tests.py repro/D01/ -v --tb=short`

## Result

```
PASSED test_observed_snapshot_archives_rows_and_maps_waiting_to_not_reached
PASSED test_control_retry_after_partial_append_has_no_loss_and_no_duplicates
PASSED test_control_retry_after_full_append_failure_copies_once
PASSED test_control_second_run_is_idempotent_and_future_tabs_are_kept
FAILED test_regression_close_must_not_drop_row_added_after_read
FAILED test_regression_late_status_change_must_not_be_archived_stale

2 failed, 4 passed
```

Failing assertions (synthetic rows, in-memory workbook `review-persistence-B`):

```
E desired contract (SETUP.md:104-105,129-130): a row written to the past-day
  tab after the backend read it must either be archived or keep the tab for
  the next run; actual: history FIOs ['Иванов Иван', 'Петрова Анна',
  'Сидоров Пётр'], tab still present=False

E desired contract (SETUP.md:104-105,129-130): the close must observe the tab
  as it was at deletion time; actual: archived status for Иванов Иван is
  'не_дошло', all statuses {'Иванов Иван': 'не_дошло', 'Петрова Анна': 'сдал',
  'Сидоров Пётр': 'отозван'}, tab still present=False
```

## Source path

`grading/queue/store.py:584-665` (`snapshot_sheet`): reads the tab (606),
builds the append list against history counts (608-636), then sends
`appendCells` + `deleteSheet` in one `batch_update` (638-664). There is no
re-read of the tab before `deleteSheet` (663) and no post-append completeness
check. The scripted reference implementation does both
(`queue-apps-script/Code.gs:156-169`).

The documented contract is shared by both closers:

- `source/docs/SETUP.md:97-105` — «Обе стороны выполняют одну и ту же
  идемпотентную операцию… 4. проверить, что все строки очереди есть в истории;
  5. удалить лист очереди, только если он не менялся с момента чтения.»
- `source/docs/SETUP.md:129-130` — «Лист изменился во время закрытия… Лист не
  удалён, следующий запуск добавит недостающие строки и закроет его.»
- `source/docs/hackathon/ADR-queue-storage.md:110-113` — the teacher works in
  the sheet directly; manual editing is a stated feature, so a past-day tab can
  be changed outside the backend.

## What retry does get right (controls, not defects)

- Append applied, `deleteSheet` failed → the tab stays; the retry copies 0 new
  rows, deletes the tab, history has each row exactly once.
- Batch failed before applying anything → tab stays; retry copies 3 rows once.
- Second run after success → 0 rows, history unchanged; today/future tabs kept.
- Status mapping: `ждёт` → `не_дошло`, `сдал`/`отозван` preserved.
- The multiset key `(date, group, fio, lab, session)` matches the documented
  history key; repeated identical registrations are preserved.

## Limits

- In-memory fake workbook whose `batch_update` mirrors the Google request shape
  (`appendCells` with `userEnteredValue.stringValue`, `deleteSheet` by id); the
  external write is injected deterministically between the read and the batch.
  Real Google Sheets, Apps Script execution and production timings were not run.
- The write window is between `read_queue_rows` and `batch_update`; in
  production it is short, but it is exactly the case SETUP.md documents
  (teacher manual edit / script close at 01:30 while the lazy backend close
  runs on the first request of the new day).
- A silent partial `appendCells` is not simulated (Sheets does not normally
  drop rows within one request), so the missing step-4 completeness check is
  noted but not claimed as a separate reproducible defect.
- The in-process lock is not treated as protection here: it serializes backend
  mutations only, and the documented scenario is an external writer. No
  multi-worker mode is claimed as a defect.
- Base comparison is static; `grading/queue/store.py`, `docs/SETUP.md` and
  `queue-apps-script/Code.gs` do not exist in the base commit.
