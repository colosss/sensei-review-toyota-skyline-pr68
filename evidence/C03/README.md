# C03 evidence — queue admission with failing CI

- Verified SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d` (base `eef98bb3`)
- Actor: `deepseek-gates-B` (isolated packet; no shared services)
- Environment: project `.venv`, Python 3.12.13, pytest 9.2.0, disposable pinned
  runtime `scratch/runtime/app` (hash-manifest checked by the runner)
- Recorder receipt: `scratch/pipeline/C03/runs/03e5d25bd5af4660a0aa03b9e681e834.json`
  (exit 1, no timeout, baseline clean, input hash recorded)
- Command:
  `.venv/bin/python scripts/review_pipeline.py run C03 --actor deepseek-gates-B --timeout 120 --artifact repro/C03/test_ci_admission.py -- .venv/bin/python scripts/run_review_tests.py repro/C03/ -v --tb=short`

## Result

```
test_control_passing_ci_admits_and_records_grade PASSED
test_control_pending_ci_is_rejected PASSED
test_failing_ci_must_not_admit FAILED
test_protected_passing_cell_with_failing_current_ci_must_not_admit FAILED
2 failed, 2 passed
```

Failing output (sanitized, synthetic student "Студент Гамма"):

```
E AssertionError: desired contract: a student whose current HEAD CI did not pass
  must not enter the defense queue (CI_NOT_PASSED); actual: register HTTP 200
  ({"position":1,"queue_size":1}), waiting rows [('Студент Гамма', 'ждёт')],
  grade cell after the call 'x'
E AssertionError: desired contract: an earlier passing run kept in a protected
  cell does not replace CI on the current HEAD; actual: register HTTP 200
  ({"position":1,"queue_size":1}), waiting rows [('Студент Гамма', 'ждёт')],
  grade cell 'v'
```

The fake GitHub transport returned exactly the documented REST shapes the
client parses: `/commits` → `[{"sha": ...}]`, `/commits/{sha}` →
`{"sha": ..., "files": []}`, `/commits/{sha}/check-runs` →
`{"total_count": 1, "check_runs": [{"name": "test", "conclusion": "failure",
"html_url": ..., "completed_at": ...}]}`, `contents` → `{"type": "dir"}`.

## Measurements (negative results, not defects)

- One admission = 8 GitHub GETs (1 workflows content + 3× commits list +
  3× commit detail + 1 check-runs). A duplicate attempt costs the same 8 calls
  before `ALREADY_IN_QUEUE`. Count is constant, not unbounded; at the supported
  10–20 students/class this does not reproduce a rate-limit failure.
- The check-runs request is made for the exact SHA returned by `get_latest_commit`
  (asserted in the passing control), so no SHA-to-check-runs mismatch was found.
- `get_latest_commit` is called three times per admission (6 of the 8 requests).
  The revision can change between calls; that TOCTOU is pre-existing in
  `grading/grader.py`/`grading/bulk.py` (unchanged by the PR) and is recorded
  separately, not as this finding.

## Scope limits

- TestClient + in-memory fake Sheets + fake GitHub HTTP only; no real
  Sheets/GitHub, no browser, no shared backend, no system-clock change.
- Only the CI gate was exercised; identity and queue-storage behaviour belong
  to other packets.
