# Q03 evidence: same FIO, different GitHub login

Pinned SHA `20bea22cf4a1cbc19634a984883ff52764ce9d6d`. Actor `deepseek-queue-B`.
Local reproduction only; no browser, no real GitHub/Sheets, no app fix.

## Receipt

```
.venv/bin/python scripts/review_pipeline.py run Q03 --actor deepseek-queue-B --timeout 120 \
  --artifact repro/Q03/conftest.py \
  --artifact repro/Q03/test_q03_same_fio_distinct_login.py \
  --artifact repro/C06/c06_fake_sheets.py \
  -- .venv/bin/python scripts/run_review_tests.py repro/Q03/ -v --tb=short
```

Receipt: `scratch/pipeline/Q03/runs/cc1cad23ece64c3bab9bc3f9df9e5c32.json`
(exit 1, not timed out, baseline clean after; all three inputs hashed).
Earlier receipt `0f4dda6461114c1d9d8b81044199b4b4.json` is superseded: the
regression assertion was relaxed from HTTP 403/404 to "non-2xx", so the
contract does not depend on a particular rejection code.

Result: **3 passed, 2 failed**:
- passed: withdraw observation, shift observation, distinct-FIO control;
- failed: withdraw regression, shift regression.

## Identity setup

Roster (fake group sheet, read by the real `_load_queue_sheet_context`):

| row | FIO | GitHub |
|---|---|---|
| 3 | Иванов Иван | `c06-ivanov-a` (A) |
| 4 | Иванов Иван | `c06-ivanov-b` (B) |
| 5 | Петрова Анна | `c06-petrova` (control) |

B's `student_session` is signed by the app's own `build_student_session` with
B's own GitHub username and roster FIO. No public `/register` is called and no
A login is claimed; B is a properly authenticated student. The app resolves
B's username to row 4, obtains FIO `Иванов Иван`, then `store` matches the
queue row by `(group, lab, fio)`.

## Observed

- A registers ЛР1 (position 1). B withdraws ЛР1 -> HTTP 200
  `{"status":"withdrawn"}`; A's row becomes `отозван`; A's status says
  `in_queue=false`.
- A (1) and Петрова (2) register ЛР1. B shifts by 1 -> HTTP 200
  `{"old_position":1,"new_position":2}`; A moves behind Петрова.
- Control: A and Петрова register; Петрова withdraws -> only Петрова's row
  becomes `отозван`, A stays `ждёт` at position 1.

## Why this is not C04

C04 used public re-registration of an already known FIO + GitHub login to
obtain a student session without proof of ownership. Here B has a valid
signed session for B's own username; the failure is that the queue has no
stable per-person key (row stores FIO only), so two real namesakes collapse
into one mutable row. No GitHub account takeover is claimed.

## Limitations

- Synthetic namesakes; a real roster can contain them, but this is not
  measured on a production sheet.
- The signed cookie is synthetic (app signer, review `SECRET_KEY`) and models
  a completed reliable OAuth; real OAuth redirect/GitHub calls were not used.
- A fix may require storing a stable identity in the queue schema; the test
  asserts behaviour (A unchanged), not an implementation.
- The rejection status is left open (non-2xx), because the requirement is
  "do not mutate another person's row".
