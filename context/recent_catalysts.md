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

- [2026-04-25 18:00Z] **hormuz_normal_end_june** · example outlet (article) —
  Shipping traffic through the strait remained at roughly 60% of the trailing
  7-day average for the third consecutive day.
- [2026-04-26 09:00Z] **trump_blockade_lifted_may31** · example wire (article) —
  No qualifying announcement has been issued. Watch for end-of-day briefings.
- [2026-05-30 13:49Z] **hormuz_normal_end_june** · @FirstSquawk (tweet) — 2h
IRAN SIGNALS IT IS STICKING TO ITS ORIGINAL POSITION IN NUCLEAR TALKS, WITH NO MAJOR CONCESSIONS EXPECTED
TEHRAN CONTINUES TO REJECT KEY U.S. DEMANDS, INCLUDING HANDING OVER HIGHLY ENRICHED URANIUM STOCKPILES AND CHANGES TO ITS CORE NUCLEAR POLICY 
#BREAKING
- [2026-05-30 13:47Z] **hormuz_normal_end_june** · @ir_rezaee (tweet) — 5h
Translated from Persian
As predicted, the President of the United States is betraying diplomacy for the third time. By continuing the naval blockade and making excessive demands in negotiations, he has once again proven that he is not inclined toward negotiation and is pursuing other objectives.
- [2026-05-30 13:45Z] **hormuz_normal_end_june** · @FaytuksNetwork (tweet) — 6h
Several U.S. service members were injured and two MQ-9 Reaper drones were seriously damaged at Kuwait's Ali Al Salem Air Base during an Iranian attack earlier this week, according to Bloomberg. CENTCOM said a missile targeting the base was intercepted by Kuwaiti air defenses on May 27, though Bloomberg reports debris from the interception still struck the installation.
- [2026-05-30 13:45Z] **hormuz_normal_end_june** · @TheIranianzg3z (tweet) — 6h
BREAKING: Five U.S. service members were injured after an Iranian Fateh-110 missile struck Ali Al Salem Air Base in Kuwait following recent U.S. operations against Iranian targets, according to Bloomberg.
The incident marks one of the most significant direct confrontations since the ceasefire began, highlighting the risk of further escalation despite ongoing diplomatic efforts.
- [2026-05-31 17:01Z] **hormuz_normal_jul31** · @MarioNawfal (tweet) — 20m
🇺🇸🇮🇷 Trump made significant edits to the Iran MOU on Friday. The revised proposal has been sent back to Tehran. No response yet.
- This is the third round of edits Trump has made to the U.S. proposal
- The edited text was sent through Pakistani mediators
- The source described the changes as "somewhat significant" without elaborating
- There is no immediate deadline
Source: CBS News
- [2026-05-31 17:00Z] **hormuz_normal_end_june** · @MarioNawfal (tweet) — 
🚨🇴🇲 Oman's Ministry of Defense issued an alert today after a suspected naval mine was sighted in its territorial waters in the Strait of Hormuz
The ministry advised all mariners to keep a safe distance from suspicious objects and report them to authorities.
All week the U.S. has struck Iranian boats it said were laying mines in Hormuz, and USNAVCENT just warned it would target any vessel doing so. 
Now a suspected mine has surfaced in the waters of Oman, the neutral state caught between Iran's claim to manage the strait and Washington's pressure on Muscat.
A live mine in the world's most important oil chokepoint is exactly the danger the deal is meant to end.
- [2026-05-31 16:58Z] **hormuz_normal_jul31** · @KobeissiLetter · (tweet) — 
6h
BREAKING: President Trump says he is "in no hurry" to make a deal with Iran and "if we don't get what we want, we are going to end it in a different way."
Last weekend, President Trump said a deal was going to be announced "shortly."
Today marks 93 days since the Iran War began.

## Noisy Social-Media And Rumour Watch

- [2026-04-26 07:00Z] **iran_us_peace_jun30** · @example_handle (tweet) —
  Sourceless rumour about a new diplomatic backchannel; no confirmed catalyst,
  social-media chatter only. Treat as non-authoritative.

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
