# C01 browser observation (manual, synthetic harness)

Date: 2026-11-11. SHA: `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Conditions: `launch.py --hold` on loopback, real built frontend served from
`scratch/runtime/app/frontend/courses-front/dist`, synthetic in-memory
Sheets/GitHub/CI, no external calls. Browser: Playwright via Zed. Screenshot:
`evidence/C01/browser-registration-queue.png`.

Steps and observations:

1. Opened `http://127.0.0.1:18281/` — real UI rendered, course list showed
   `Synthetic Review Course` (data from `GET /courses` on `:18280`).
2. `Выбрать` -> `/course/review-c01`, groups `4431`, `4432` from synthetic
   Sheets.
3. Opened group `4431` -> lab `ЛР1` -> `/course/review-c01/group/4431/lab/ЛР1`.
4. Registration form accepted `Иванов / Иван / Иванович / review-ivanov`;
   response `registered`, synthetic CI returned `updated`, result `v`.
5. Queue panel then showed queue open, existing entry `Петрова` position 1,
   and enabled `Записаться`.
6. Clicked `Записаться` -> `Вы в очереди: позиция 2 из 2`; queue list showed
   Петрова (1, ждёт) and Иванов (2, ждёт).
7. `POST /__harness__/reset` restored the initial roster/queue
   (`Иванов` github empty, only Петрова waiting).

Network/console notes:

- Public UI requests used `http://127.0.0.1:18280/...` (the served bundle was
  rewritten from the build-time `http://localhost:8000`); they succeeded via
  the app's CORS middleware (`allow_origin_regex=".*"` + credentials).
- A request to the static origin for relative `/api/v1/...` returns 404 from
  the harness static server. This mirrors the stock `nginx.conf` (no proxy).
  Admin pages use those relative URLs; the student path does not.

Limits: synthetic CI/GitHub/Sheets; no real integration. This observation
does not by itself establish a PR defect: the port mismatch is inherited and
the missing proxy does not break the student path that uses the absolute API
base URL.
