# T01 evidence — team identity, group/lab isolation, lock/cache keys

- Verified SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d` (base `eef98bb3`)
- Actor: `deepseek-durable-B`; queue-only, supported single-process paths
- Environment: project `.venv`, Python 3.12.13, pytest 9.2.0, hash-pinned
  disposable runtime `scratch/runtime/app`
- Recorder receipt: `scratch/pipeline/T01/runs/f1ed41d2dc5d48fab9beb956cbe28495.json`
  (exit 0, no timeout, baseline clean after, test input hashed)
- Command:
  `.venv/bin/python scripts/review_pipeline.py run T01 --actor deepseek-durable-B --timeout 120 --artifact repro/T01/test_t01_teams_isolation.py -- .venv/bin/python scripts/run_review_tests.py repro/T01/ -v --tb=short`

## Result: 8 passed, 0 failed

```
PASSED test_team_member_resolution_is_lab_scoped_and_case_insensitive
PASSED test_unreadable_roster_blocks_instead_of_silently_reporting_no_team
PASSED test_individual_lab_returns_none_without_github_calls
PASSED test_team_title_uniqueness_makes_the_queue_title_identity_safe
PASSED test_team_list_cache_is_keyed_by_org_and_prefix
PASSED test_team_rows_are_isolated_by_group_and_lab
PASSED test_queue_cache_key_separates_course_group_lab_and_day
PASSED test_lock_keys_scope_and_serialize
```

In the tested area no defect was found; this is a refutation of the incoming
suspicion, not a proof that the whole team/queue path is correct.

## What each check establishes

1. **Membership** — `resolve_team_for_user` resolves the signed login
   case-insensitively (`ALICE` → team), includes pending invitees, ignores
   another lab's team (prefix `os-task4`), and returns `NO_TEAM` for a
   teacher collaborator (`course.github.teachers`) and for an org owner with
   `admin` permission.
2. **Unknown roster** — one unreadable team makes an unaffiliated student get
   `TEAMS_UNAVAILABLE`, not a silent `NO_TEAM`; a student in a readable team
   still resolves.
3. **Non-team lab** — `resolve_team_for_user` returns `None` without a single
   GitHub call.
4. **Title as queue identity** — `TeamRegistry.create_team` returns
   `TITLE_TAKEN` for a case-insensitive duplicate title before provisioning.
   Since queue rows for teams use the title, this check is what makes the
   identity safe (for teams created through the app).
5. **Team-list cache keys** — cache hit for the same `(org, prefix)`; separate
   entries for a different lab prefix and a different org; `invalidate`
   refetches.
6. **Storage isolation** — the same team title registered in `4431/ЛР5`,
   `4432/ЛР5` and `4431/ЛР6` produces three independent rows with their own
   positions; `list_waiting`/`find_waiting` do not cross group or lab.
7. **Queue cache keys** — `(course, group, lab, day)` separate entries; the
   same key is served from cache.
8. **Locks** — `sheet_lock`/`locked_course` are keyed by spreadsheet id and do
   serialize two threads on the same id; `lab_lock` is keyed by
   `(course, canonical lab key)`.

## Limits

- Fake GitHub payloads only (`list_org_repos`, `list_collaborators`,
  `list_invitations` shapes the client parses); no real GitHub, no network.
- The team *endpoint* path (`queue_register`/`status` with `_resolve_queue_team`)
  is not driven through HTTP here; the resolver, store keys and registry are
  checked directly. C04/C06 cover the HTTP session/list scopes.
- The queue read cache (`grading/queue/cache.py`) is imported but not called by
  the queue endpoints in the pinned code (C06 observation); the cache-key test
  is therefore a unit-level check of the module, not of an HTTP path.
- A manually created team repository with the same display title as an app
  team could break the title identity; no requirement covers manual repos.
  Membership/title of teams created outside `create_team` is out of scope.
- Team-to-group binding is not required anywhere in the docs; a team whose
  members have sessions for different groups can produce one row per group.
  This is recorded as a policy gap, not a defect.
- Single-worker operation is the documented constraint and is not claimed as a
  defect; no multi-process race was tested.
- Base comparison: `teams_bridge.py`, `locks.py`, `cache.py` are new in the PR;
  `grading/teams.py` exists in the base and was not modified, so its caching
  and roster semantics are inherited.
