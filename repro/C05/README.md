# C05 — older refresh overwrites a successful queue join

SHA `20bea22cf4a1cbc19634a984883ff52764ce9d6d`. Real built frontend and real backend routes on the isolated harness in `repro/C01/README.md`. Google Sheets, GitHub, CI and schedule are synthetic. No live integrations.

Start that harness with a finite lifecycle under coordinator control. UI: `http://127.0.0.1:18281`; API: `http://127.0.0.1:18280`.

Run `browser_stale_reload.js` as a Playwright function snippet through `browser_run_code_unsafe` with filename. It resets only the synthetic fixture, clears cookies, opens lab1 and fills synthetic Ivanov data. It delays delivery of ONE real GET /queue fetched before registration. It does not change bytes. After registration and its reload render Ivanov, it releases the older response; the prior reload replaces current status/list with pre-join data. It inspects stored rows and demonstrates recovery with Refresh.

This is an observation scenario with explicit guards for the observed contradiction; successful execution is NOT a green regression of correct behaviour. Expected correct behaviour: an older response cannot erase the state fetched after a successful mutation.

Manual equivalent: on a fresh lab page fill the form, click Refresh, delay its list response in devtools/proxy, click Join while Refresh is pending, let join and post-join reads complete, then deliver old list bytes. Success notice stays, own row disappears, Join is offered although storage still has the row. Refresh restores it.

Precise output: afterJoin `position 2 of 2` + Petrova/Ivanov; afterOldRead success notice + only Petrova + Join; stored queue still has Ivanov pos2 waiting; afterRefresh own row returns. No arbitrary sleeps, response fabrication or backend changes. The ordering is controlled, not a claim that it was the exact cause of the colleague's screenshot or that production latency/TTL were measured. The script returns no credentials/headers. It cleans route interception in finally; it does not stop the coordinator-owned stand.
