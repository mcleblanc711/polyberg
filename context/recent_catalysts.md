# Recent Catalysts

Manually curated short-horizon news, rumours, and missing-info notes that the
packet builder embeds into the LLM-facing context block. This file ships with
**sample entries** in the public repo.

The packet builder reads this tracked file directly — there is no
`recent_catalysts.local.md` overlay on the CLI side. If you want to keep a
private reference copy off-repo, save it as `recent_catalysts.local.md`
(gitignored) and either swap it in locally when building a packet or feed
entries through the GUI's Intake tab, which writes back to this tracked file.

Each entry should be tagged to a `market_id` from `context/market_registry.yaml`
so the packet builder can route it correctly.

## Credible Reporting Watch

- [2026-04-25 18:00Z] **hormuz_normal_may15** · example outlet (article) —
  Shipping traffic through the strait remained at roughly 60% of the trailing
  7-day average for the third consecutive day.
- [2026-04-26 09:00Z] **trump_blockade_lifted_apr30** · example wire (article) —
  No qualifying announcement has been issued. Watch for end-of-day briefings.

## Noisy Social-Media And Rumour Watch

- [2026-04-26 07:00Z] **cl_high_120_end_june** · @example_handle (tweet) —
  Front-month Brent softening overnight; no confirmed catalyst, demand-side
  noise only. Treat as non-authoritative.

## Trader Interpretation Notes

- The Hormuz data-oracle markets should be judged by Portwatch mechanics
  rather than headline tone.
- Announcement markets can flip on a single qualifying statement; favour
  laddered exits.

## Unresolved/Missing Information

- Need an authoritative IMF Portwatch print for the 7-day moving average as of
  the prior trading day.
- Need confirmation of whether any US official statement counts under the
  blockade-lifted resolution rule (see `context/stable_rules.md`).

## Notes

- All entries here are illustrative. Replace with your own curated entries in
  this file, or import via the GUI's Intake tab.
- Treat Twitter/X items as noisy and non-authoritative; they are catalyst
  signals only, never resolution evidence.
