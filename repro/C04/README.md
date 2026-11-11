# C04 — identity authority over another student's queue record

SHA under review: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`
Base commit for the PR comparison: `eef98bb373c71e9e4e7df4258e1fe5b4b4c5ac39`
Actor: `deepseek-c04-A`

## Invariant

A signed student session must act only on the queue record of the student it
belongs to. An unauthenticated visitor who only repeats publicly available
data (exact ФИО and a public GitHub login) must not obtain authority over
another student's waiting record through the public registration form and then
withdraw or shift it.

## Sources of expected behaviour

- `source/docs/hackathon/ADR-queue-storage.md:23-28` — students read their own
  status/position and write only their own registration, withdrawal and shift;
  the teacher marks results.
- `source/grading/queue/session.py:55-72` — the queue identity contract is a
  signed, scope-checked session; identity is not supposed to come from request
  body fields.
- `source/main.py:2940-2945` — `_require_student_session` authorizes
  register/withdraw/shift solely from the `student_session` cookie.
- `source/main.py:1016-1055` — that cookie is built from public registration
  form data; the GitHub check at `main.py:1000-1006` only proves that the login
  exists (`GET /users/{login}`), not that the requester owns it. When the sheet
  row already contains the same login, the endpoint answers
  `already_registered` and still issues the cookie.
- `source/main.py:3037-3060`, `3604-3612` — the OAuth queue flow issues a
  separate signed `queue_session`, but no register/withdraw/shift path reads it
  (`require_queue_session` is imported and never called). The actual authority
  for queue mutations is the unverified `student_session`.

## Reproduction

From the review root, one isolated pytest process through the review harness:

```bash
.venv/bin/python scripts/run_review_tests.py repro/C04/ -v --tb=short
```

The harness runs the disposable, hash-pinned runtime copy of the app and blocks
external network. The test itself:

- builds a fresh in-memory fake spreadsheet per test, id `review-c04-sheet`
  (group sheet, `Очередь-2026-11-08`, `История_очереди`);
- injects course/lab, session window, today's date and group ids through the
  app's own seams (`get_course_by_id`, `_queue_active_session`,
  `_queue_today_str`, `_schedule_group_ids`);
- replaces only the GitHub "user exists" request with a contract-compliant
  fake response and disables rate limiting (out of scope);
- calls the real endpoint functions through `TestClient(main.app)` with four
  independent cookie jars: student A, student B, student C, anonymous;
- never prints, stores or asserts on cookie/token values.

## Observed result (pinned code)

```
test_unauthenticated_and_peer_sessions_cannot_withdraw_b PASSED
test_public_registration_of_another_identity_cannot_withdraw_b FAILED
test_public_registration_of_another_identity_cannot_shift_b FAILED
```

- Control: no cookie → withdraw `401`; a genuine peer session (A) → `404`
  and B's record unchanged. These pass, so queue scoping works for a genuinely
  owned session.
- Violation: anonymous `POST .../register` with B's exact ФИО and B's GitHub
  login returns `200 already_registered` **and sets a student session**. The
  same client then `POST .../queue/withdraw` → `200`; B's row changes from
  `ждёт` to `отозван`.
- Violation: same escalation with `POST .../queue/shift {"delta": 1}` → `200`;
  B's position moves `1 → 2` ahead of C.

Desired contract asserted by the failing tests: the foreign mutation is
rejected (`401/403`) and B's status/position stay unchanged.

## PR relation

`introduced` for the queue authority. The public registration form itself is
inherited from the base commit, but in the base it issued no session and there
were no queue routes:

- `git show eef98bb:main.py | grep -n "STUDENT_SESSION\|build_student_session\|def queue_"` → none.
- `git show eef98bb:grading/queue/session.py` → path does not exist at base.
- Base registration has the `existing_github == student.github` branch but no
  `set_cookie`; the cookie issuance and the queue endpoints are added by the
  PR.

So "typing another person's name" is not the defect by itself. The defect is
that the PR turns that unverified form submission into signed authority used
by register/withdraw/shift, while the OAuth-verified `queue_session` it also
adds is never enforced.

## Limitations

- Fake Sheets/GitHub clients; no real Google Sheets, GitHub or HTTP server.
  Behaviour of the real integrations (quota, locale, OAuth callback) is not
  exercised.
- The attacker must know the target's exact ФИО and GitHub login. ФИО is
  returned by the public queue list (`main.py:3433-3444`); GitHub logins are
  public, but how a peer discovers them in this UI was not tested.
- Individual (non-team) labs only. Team resolution is out of this packet.
- Sequential requests; no race conditions. Rate limiting is disabled in the
  test; the production limit (10/min) does not prevent this attack.
- `SECRET_KEY` has a default fallback in the app, but the review harness sets a
  synthetic secret; cookie forgery is not part of this finding.
