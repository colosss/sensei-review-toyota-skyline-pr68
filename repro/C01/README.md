# C01 — isolated browser harness for pinned PR #68

Harness for reviewing the **pinned** submission `20bea22cf4a1cbc19634a984883ff52764ce9d6d`
without Google Sheets, GitHub, Docker or network access.

- Real built frontend: `scratch/runtime/app/frontend/courses-front/dist` (served as-is).
- Real backend routes: `scratch/runtime/app/main.py` imported read-only.
- Synthetic data: two groups, a student roster, one active defense session and a
  daily queue, all in process memory.
- Fake boundaries: gspread-compatible in-memory workbook, fake GitHub user
  lookup, synthetic passing CI. Every other outbound HTTP call raises.

Nothing under `source/`, `scratch/runtime/`, or shared docs is modified.

## Ports and URLs

| Service | URL |
|---|---|
| Real built UI | `http://127.0.0.1:18281/` |
| Pinned backend | `http://127.0.0.1:18280` |
| Health | `http://127.0.0.1:18280/__harness__/health` |
| Inspect synthetic state | `http://127.0.0.1:18280/__harness__/state` |
| Reset fixture (POST) | `http://127.0.0.1:18280/__harness__/reset` |
| Harness contract | `http://127.0.0.1:18280/__harness__/contract` |

Both servers bind `127.0.0.1` only.

## Finite selftest (no server left running)

```bash
.venv/bin/python repro/C01/harness/launch.py --selftest \
  --report evidence/C01/harness-selftest.json
```

Starts both children, checks the public registration path, the queue, the
admin read-only queue and `set-status` API, static bundle rewriting, then
terminates everything and exits 0.

## Coordinator / Playwright lifecycle

Start the harness as a Playwright **server child process** and stop it via
`SIGTERM`. `--hold` is the only long-running mode; it forwards termination to
both children.

```bash
.venv/bin/python repro/C01/harness/launch.py --hold
# ready line: {"event":"harness_ready","ui":"http://127.0.0.1:18281/",...}
```

Playwright sketch:

```js
const server = spawn(".venv/bin/python",
  ["repro/C01/harness/launch.py", "--hold"], {stdio: "pipe"});
// wait for the harness_ready line, then:
await page.goto("http://127.0.0.1:18281/");
// ... scenario ...
server.kill("SIGTERM"); // launcher stops backend and static children
```

Reset between scenarios:

```bash
curl -sS -X POST http://127.0.0.1:18280/__harness__/reset
curl -sS http://127.0.0.1:18280/__harness__/state
```

## Synthetic fixture

- Course `review-c01`; groups `4431`, `4432`; two labs:
  key `1` / short `ЛР1` / `github-prefix: lab1` and
  key `2` / short `ЛР2` / `github-prefix: lab2`. Both are allowed in the
  synthetic active session (`allowed_lab_ids=["1", "2"]`).
- Roster (`{surname name patronymic}` must match exactly):
  - `4431`: `Иванов Иван Иванович` (free), `Петрова Полина Сергеевна`
    (`review-petrova`), `Сидоров Олег Петрович` (free).
  - `4432`: `Альфа Алина Андреевна` (free), `Бета Борис Борисович`
    (`review-beta`).
- There is exactly one `Иванов Иван Иванович`; no duplicate-FIO roster row is
  added on purpose. The pinned registration path resolves an exact FIO to the
  first matching row (`main.py:register_student`), so a duplicate name would
  make the target row ambiguous. The same student can be exercised on both
  `ЛР1` and `ЛР2` without a second roster entry.
- Active session `review-slot-2`, 10:40–12:10, room `A-101`; queue sheet
  starts with Петрова waiting at position 1.
- Registration accepts any synthetic GitHub login because the fake
  `api.github.com/users/{login}` returns 200.
- Synthetic CI returns `updated`, grade `v`.

## Deliberate overrides (disclosed)

| Boundary | Override |
|---|---|
| Google Sheets | `sheets_client` -> `FakeSheetsClient` with in-memory roster/queue/history |
| Course config | one synthetic course instead of `courses/*.yaml` |
| Schedule | one active session instead of `schedules/*.yaml` |
| GitHub | only `GET api.github.com/users/{login}` -> fake 200; all other methods raise |
| CI | `evaluate_student` / `ensure_ci_passed` -> synthetic pass with real return objects |
| Frontend API base | static server rewrites the build-time `http://localhost:8000` **in the served bytes only** to `http://127.0.0.1:18280`; the dist and app files are unchanged |

HTTP routes, request models, cookie signing, queue store logic and gspread
usage are not replaced.

## What this harness shows for C01

- The student path (`/courses`, groups, labs, register, grade, queue) uses the
  absolute API base from `src/api/index.js` and works against the backend on a
  different origin through the app's CORS middleware. **Absence of an nginx
  proxy is not by itself a defect for this path.**
- Admin pages use relative `/api/v1/...` URLs. The static origin intentionally
  has no `/api` proxy, so those requests return 404 there — the same as the
  stock `nginx.conf`, which has no `proxy_pass`.
- The stock Compose file publishes frontend `8080:80` while nginx listens on
  `8080`; that mismatch is independent of the proxy question and is inherited
  from the PR base (see `reproduce_stock_config.py`).

## Limits

- CI and GitHub are synthetic; this harness does not prove real GitHub or
  Sheets integration.
- The fake schedule is one session and does not exercise GUAP/manual
  corrections, week parity or timezone boundaries.
- Rate-limit buckets are in-process; `reset` clears them, but a long browser
  scenario can still hit the pinned per-route limits.
- No Docker/nginx is executed: the stock port mismatch is established from the
  pinned files, not from starting the Compose project.
- In-memory state disappears when the launcher exits; no disk writes except
  sanitized harness logs under `scratch/pipeline/C01/runtime/`.
