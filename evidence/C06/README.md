# C06 evidence: queue numbering and list scope

Pinned submission: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`
PR base: `eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39`
Actor: `deepseek-queue-B`. Local reproduction only; no publication, no app fix, no `source/` writes.

## What was run

```
python3 scripts/verify_baseline.py            # pinned and clean before/after
.venv/bin/python scripts/run_review_tests.py repro/C06/ -v --tb=short
```

Recorder receipt: `scratch/pipeline/C06/runs/96bbbc9bcab342b39396bb7b7341a52a.json`
(target exit 1, not timed out, baseline clean after). Raw log: same `runs/` directory.

Final result: **6 observation tests pass, 4 desired-contract regressions fail**.
The four failures are one per independent cause; the observations are scenario
evidence, not "passing bug tests" for the regressions.

## Isolation

* real FastAPI endpoints through `TestClient` (`/queue`, `/queue/status`,
  `/queue/register`, `/queue/withdraw`, `/queue/shift`,
  `/admin/.../queue/set-status`) - the same calls the frontend makes;
* fresh in-memory workbook per test (`review-c06-sheet`), synthetic roster:
  two students both named `Иванов Иван` with different GitHub logins, plus
  `Петрова Анна`; labs `ЛР1`/`ЛР2`, groups `B-G1`/`B-G2`;
* `_load_queue_sheet_context` stays real and resolves FIO from the fake group
  worksheet; the course config, sheets client, CI check and GitHub client are
  replaced by the app's own seams; queue-session clock is switched between
  requests (pair 1 -> pair 2) instead of using wall time;
* no real Sheets, GitHub, network, browser or file writes; no app YAML change.

## Primary reproduction (screenshot state)

Chain: register `Иванов`(GitHub A) on `ЛР1` -> register `Иванов`(GitHub B, same
FIO) on `ЛР2` -> register `Петрова` on `ЛР1` -> `POST .../shift {"delta":1000}`
for `Иванов` on `ЛР1`.

Observed over HTTP (pinned code):

| call | result |
|---|---|
| status before shift (`ЛР1`) | `in_queue=true`, `position=1`, `queue_size=2` |
| shift 1000 | `200 {"old_position":1,"new_position":2}` |
| status after shift | `in_queue=true`, `position=2`, `queue_size=2` |
| list `.../labs/1/queue` | positions `[2, 1, 1]`, labs `[ЛР1, ЛР2, ЛР1]`, FIO `[Иванов, Иванов, Петрова]` |
| list `.../labs/2/queue` | the identical three rows |

This is the reported UI state: own status "2 из 2" next to three numbered rows
2, 1, 1 with two identical `Иванов` labels. The list response is the whole
`Очередь-YYYY-MM-DD` sheet; the path's `group`/`lab` are not applied
(`source/main.py:3416-3448`). `QueueSection` renders every returned row in
server order and uses the stored `position` as the chip
(`QueueSection.jsx:328-359`, `api/index.js:45-46,88-92`).

## Independent causes (kept separate)

1. **List scope** - `GET .../labs/{lab}/queue` returns every row of the day
   sheet (all labs and groups). Red regression:
   `test_c06_screenshot_chain.py::test_regression_lab_page_list_is_scoped_to_requested_group_and_lab`.
   Group leakage observed separately in
   `test_observed_list_mixes_other_groups_too`.
2. **Session scope of numbering** - `register` computes `position` from the
   active pair only (`store.py:426-433`), while status/list/withdraw/shift/
   set-status operate without a session filter (`main.py:3101,3169,3318,3357,3404`).
   Two students registering in pair 1 and pair 2 of the same lab both get
   position 1: list `[1, 1]`, status "position 1 of 2". Red regression:
   `test_c06_session_scope.py::test_regression_position_is_unique_for_one_group_lab_day`.
3. **set-status never renumbers** - `queue_set_status` passes `group_ids` in the
   `session_no` positional slot (`main.py:3529-3531` vs `store.py:507-516`), so
   `_renumber_waiting` filters `row.session_no == [group ids]` and updates
   nothing. After the first of two students is marked "сдал", the remaining
   student is alone but reports "position 2 of 1". Red regression:
   `test_c06_set_status_renumber.py::test_regression_set_status_renumbers_the_remaining_waiting_queue`.
4. **Stale position of a withdrawn row** - `withdraw` renumbers only waiting
   rows (`store.py:384-397,468`); the withdrawn row keeps position 1, the next
   student is renumbered to 1, and the list (which returns all statuses)
   renders both as 1. Withdraw + rejoin also shows the same person twice
   (`[отозван 1, ждёт 1, ждёт 2]`). Red regression:
   `test_c06_withdraw_rejoin.py::test_regression_displayed_positions_are_unique_after_withdraw_and_rejoin`.

Separate, not asserted as a C06 defect: identity is FIO, not GitHub. With two
roster rows named `Иванов Иван` (different GitHub), the second student's status
resolves to the first student's waiting row (`in_queue=true`, position 1) and
their register returns `409 ALREADY_IN_QUEUE`
(`test_c06_same_fio_identity.py`). This is an observation for C02/C04 review,
because the earlier green C02 store tests use one identity only.

## Contract basis

* `queue_list` docstring/path: "List the active queue for a group and lab"
  (`source/main.py:3418-3419`), and the frontend calls it per group/lab
  (`api/index.js:45-46`).
* `queue_status` computes `queue_size` with `list_waiting(rows, group, lab)` and
  the personal `position` from the same scope (`main.py:3101,3169,3211-3223`),
  so the same screen promises "position 2 of 2" while the list shows 3 rows.
* ADR: one daily queue with a stored position, group, FIO, lab, pair
  (`source/docs/hackathon/ADR-queue-storage.md:20-25`); a position is the
  queue's ordinal, so two rows at position 1 in one group/lab/day contradict it.
* `store.set_status` itself calls `_renumber_waiting` (`store.py:543`); the
  positional call bug defeats that stated intent.

## Limitations and likely objections

* In-memory fake Sheets and `TestClient`, not a real Google Sheet, real
  schedule or browser. UI rendering is established from the frontend source
  (`QueueSection.jsx`), not from a browser session (the coordinator owns the
  browser; this actor did not use it).
* The screenshot does not identify the students, labs or sequence. The chain
  reproduces the visible state exactly with synthetic data; other sequences can
  produce the same chips (e.g. withdraw + rejoin).
* The authors may argue the day sheet is intentionally one teacher-facing
  queue. Counter-evidence: the same student page reports a group/lab-scoped
  `queue_size`, the endpoint says "for a group and lab", and `QueueSection`
  offers no lab/group marker, so two position-1 rows are ambiguous.
* Position uniqueness is inferred from the status counter and the UI chip, not
  from a literal prohibition of duplicates in the ADR.
* The pair-switch scenario assumes earlier-pair rows remain "ждёт"; the
  implementation has no per-pair close, so this follows from the code, but an
  author may call it an unsupported flow.
* A withdrawn/passed row can be argued to be history. However, the list
  endpoint returns it in the same "active queue" list and the UI shows its
  position chip; a fix could instead exclude non-waiting rows from this list.
* Cache: `_get_queue_cache` is imported but never called; `status`/`list` read
  the sheet directly. No TTL-delay was observed on this path, so C05-style
  "appears later because of cache" is not supported here. Real Sheets latency
  and the browser were not tested.
* Base comparison is static; base behavior was not executed. The queue
  package/endpoints/UI are absent in the base commit (see
  `base-comparison.txt`), so the cited lines are introduced by this PR.
