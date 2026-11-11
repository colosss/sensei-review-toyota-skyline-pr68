# S01 evidence — per-lab schedule cancellation is ignored for an all-labs slot

- Verified SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d` (base `eef98bb3`)
- Actor: `deepseek-gates-B` (isolated packet; no shared services)
- Environment: project `.venv`, Python 3.12.13, pytest 9.2.0, disposable pinned
  runtime `scratch/runtime/app`
- Recorder receipt: `scratch/pipeline/S01/runs/00ab671890194b93abe5f9010d6d5411.json`
  (exit 1, no timeout, baseline clean, input hash recorded)
- Command:
  `.venv/bin/python scripts/review_pipeline.py run S01 --actor deepseek-gates-B --timeout 120 --artifact repro/S01/test_schedule_gate.py -- .venv/bin/python scripts/run_review_tests.py repro/S01/ -v --tb=short`

## Fixture

Temporary `tmp_path/review-s01-N.yaml` (never `source/schedules`), one group
`4431`, Monday slot `guap-mon-2` 10:40–12:10, `auto_open_minutes_before: 30`,
`auto_close_minutes_after: 30`, managed clock `2026-11-09 12:00` (Monday,
week 46, inside 10:10–12:40), correction on the same date:

```yaml
    corrections:
      - id: cancel-lab3-mon-2
        date: '2026-11-09'
        remove_slots:
          - slot_id: guap-mon-2
            labs: ['3']
```

The regression fixture has no `labs:` key on the slot and no `queue_settings`
(the shipped `schedules/dev-course.yaml` and every GUAP-imported slot have this
shape). The control fixture adds `labs: ['1', '3']` to the same slot.

## Result

```
test_control_no_correction_allows_any_lab PASSED
test_control_time_window_closes_after_auto_close PASSED
test_control_correction_works_for_explicit_lab_list PASSED
test_cancelled_lab_must_be_closed_for_all_labs_slot FAILED
1 failed, 3 passed
```

Failing output (synthetic student "Студент Дельта"):

```
E AssertionError: desired contract: schedule-config.md says remove_slots[].labs
  cancels only those labs in the slot, so lab 3 must be closed; actual:
  register HTTP 200 ({"position":1,"queue_size":1}),
  queue rows for ЛР3 [('Студент Дельта', 'ЛР3', 'ждёт')]
```

The passing controls isolate the cause: the window is open at the managed clock,
all labs are allowed without a correction, and the very same correction does
close lab 3 when the slot carries an explicit `labs` list. The shipped admin
dialog builds exactly this correction (`remove_slots: [{slot_id, labs}]`,
`frontend/.../admin/CorrectionsDialog/index.jsx:229`) without requiring the slot
to list its labs.

## Separate candidate (not this packet)

The documented `remove_slots` element key is `id`
(`source/docs/schedule-config.md:273,286-293`), while validation requires
`slot_id` (`source/grading/schedule/manual.py:144-147`). A YAML copied from the
documentation raises
`ScheduleConfigError: group '4431' corrections[0]: remove_slots[0] requires slot_id`
(scratch probe `scratch/pipeline/S01/probe_doc_key.py`). Different cause from
the missing lab materialization; proposed as its own candidate.

## Scope limits

- The schedule gate was exercised through the real `main.queue_register` with
  the real `active_session_for`, but `ensure_ci_passed` was stubbed (CI is C03),
  so this says nothing about CI admission.
- Only manual-YAML sources were used; GUAP import was not run and no external
  requests were made.
- The test states the behaviour documented by the PR itself; the hackathon's
  original task text is not available in this workspace, so no stronger
  requirement is claimed.
