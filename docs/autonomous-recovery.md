# Autonomous screening recovery

## Findings and changes
- Old freshness logic skipped only weekends, so a holiday could be selected as a nonexistent target session. The verified IDX/KSEI 2026 calendar now determines the last completed session in Asia/Jakarta, using 16:15 WIB as a conservative publication boundary.
- The historical backtest (up to 180 minutes) shared one concurrency group with EOD screening. Their files are disjoint; backtest now has its own writer group, removing that avoidable queue dependency. Forward-test recovery remains serialized with screening.
- Default checkout could retain the triggering SHA after waiting in a queue. Data writers now explicitly check out current main; screening freshness runs after checkout. Old recovery session requests cannot force an earlier session.
- Old freshness checked only dates and set membership; an invalid same-session feed could look complete. It now checks quality gates, IHSG provenance, exact universe including duplicates, and accounting for processed/unprocessed names.
- Radar had a single publication push while independent writers could advance main. It now retries bounded fetch/rebase/push, preserving source-hash guards.
- Independent Published Data Reconciliation checks screening, IHSG, Purbaya, rotation/history, Radar source hashes, and GitHub's Vercel status. It requests only the missing stage, never old-run retries or validation workflows.

## Recovery limits
Primary EOD checks run at :11/:41 from 16:11 to 23:41 WIB on weekdays.
The independent reconciler runs at :23/:53 between 17:23 and 03:53 WIB daily.
No stale-session recovery is dispatched before 18:00 WIB for that day's session.
The prior completed session can be recovered on weekends/holidays or after midnight.
A valid primary feed is never rebuilt just because a component is missing.

At most one recovery dispatch per stage per completed session is allowed.
Primary recovery also recognizes older manual/agent dispatches without markers.
Active jobs prevent duplicates; the reconciler itself is serialized. Requests
always target main and carry a visible session marker. Already-used recovery
budgets fail visibly for investigation instead of looping or falsifying data.

All generation quality gates and last-valid publication behavior remain in place.
Missing prices/history remain unavailable; partial coverage is not intrinsically
a broken pipeline. Supplemental Purbaya indicators do not change scores/signals.
Historical VWAP/Wyckoff statistical validation schedules are not activated.

## Evidence and remaining external boundaries
The reconciler uploads a compact pipeline-health artifact and writes Actions
Summary; a green skipped screening job alone is not proof of fresh data.
Production JSON currently requires authentication. The reconciler verifies repo
JSON and official GitHub Vercel commit status, not an authenticated browser's JSON.
A failed Vercel status stops with an explicit error; it never creates dummy
commits, changes billing/security settings, or extracts credentials to redeploy.

GitHub documents that scheduled events can be delayed or dropped under load:
https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
No workflow hosted on GitHub can recover if GitHub stops all its own schedules
and runner execution. A separately hosted trigger would be needed for that
failure domain; none is silently purchased or provisioned here.

Calendar references: IDX Peng-00171/BEI.POP/09-2025, cross-checked with KSEI
PENG-0002/DIR/KSEI/0126 (22 closures, including Dec 24/25/31).
https://www.idx.id/id/berita/jadwal-libur-bursa
https://web.ksei.co.id/files/Pengumuman_Hari_Libur_dan_Cuti_Bersama_PT_KSEI_Tahun_2026.pdf
The explicit calendar expires after 2026; unknown years fail closed and require
a reviewed official update, rather than inventing holidays.

## Tests
python -m unittest discover -s tests -p test_pipeline_recovery.py -v
python -m automation.validate_workflows  # PyYAML + bash, provided in CI


