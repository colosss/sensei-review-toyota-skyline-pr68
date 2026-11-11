# C07 admin observation — read-only queue is deliberate

SHA `20bea22cf4a1cbc19634a984883ff52764ce9d6d`.

Hypothesis (CANDIDATES.md): "the administrator is shown the queue but cannot
do anything". Result: **not a defect in the pinned version** — the documented
contract is that the teacher manages defense results directly in Google
Sheets, while the web admin screen is a read-only viewer.

## Primary source

`docs/hackathon/ADR-queue-storage.md`:

- Variant 3 (Google Sheets) is chosen; the teacher works with the sheet
  directly, using filter views, the status dropdown and manual editing
  (lines 106–113).
- "Кто пишет": students register/withdraw/shift; the teacher marks the
  defense result (lines 26–28).
- Consequences: filter views, data-validation dropdown on "Статус", Apps
  Script closes the day (lines 121–130).

## Implementation

- `QueueViewDialog.jsx:32–38` explicitly documents "Read-only defense queue
  viewer for teachers ... No action buttons: status changes happen in the
  Google Sheet directly."
- The read-only admin page `AdminQueuePage.jsx` loads
  `/api/v1/admin/courses/{course_id}/queue/today`.
- Admin API does include `POST .../queue/set-status` (main.py:3507) and
  `POST /admin/courses/{course_id}/queue/snapshot` (main.py:3541). They exist
  as API operations; not exposing them as buttons in the read-only viewer is
  consistent with the ADR.

## Harness check (synthetic)

`repro/C01/harness/launch.py --selftest` (report:
`evidence/C01/harness-selftest.json`) logs in as the synthetic admin and
observes:

- `POST /admin/login` -> 200;
- `GET /admin/check-auth` -> 200;
- `GET /admin/courses/review-c01/queue/today` -> 200 (viewer works);
- `POST .../queue/set-status` -> 200 and the queue row changes to `сдал`.

So the mandatory teacher operation (marking the result) is available in the
supported workflow — directly in the sheet, and also via the admin API — and
the absence of buttons is not an unavailable mandatory operation.

## Limits

- Google Sheets is synthetic; this evidence does not prove real Sheets UI
  behaviour, only that the pinned code/ADR/UI contract is consistent.
- "Calling the next student" is not a separately required operation in the
  ADR; it is not asserted as missing.
