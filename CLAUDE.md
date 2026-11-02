# Socios.com Partner fixtures: handover notes

Read this first. It explains what this repo does, how it's run, the decisions already made
and the traps already found. Last updated 02/11/2026.

## What it does

Twice a week, a GitHub Actions job collects the upcoming **home** fixtures for 53
Socios.com partners (clubs and national teams). It then:

1. updates `output/fixtures.xlsx` in this repo, which people download from GitHub, and
2. posts to the Slack channel **#partner-fixtures** in the **mediarex** workspace about new
   cup, European or international fixtures, and about date or kick-off changes.

Everything uses free data sources. There's no server: it all runs in GitHub Actions.

- Repo: https://github.com/carola-jpg/Socios.com-Partner-fixtures (owner: Carola, carola@chiliz.com)
- Slack app: "partner-fixtures" (Incoming Webhook) in the mediarex workspace, created at api.slack.com/apps

## The person you're working with

Carola isn't a developer. Explain things in plain words, give short progress updates
on anything slow, and say what's happening rather than going quiet during long runs.
She has asked for:

- dates as **DD/MM/YYYY** everywhere (Excel and Slack)
- kick-off in the **stadium's local time (with UTC offset) and in UTC**
- Slack alerts only for **new cup/European/international fixtures** and **date/time
  changes**, and only for matches **at least 5 days away**
- head-to-head going back as far as practical (currently **10 seasons**, from 2016-17)

## How it runs

| Workflow | When | What |
|---|---|---|
| `.github/workflows/fixtures.yml` ("Partner fixtures") | Mon and Fri **06:43 UTC**, plus manual "Run workflow" (has a *debug* tick box) | Collects fixtures, writes Excel, posts to Slack, then commits `data/` and `output/` back to `main` |
| `.github/workflows/slack-test.yml` ("Slack test") | Manual only | Posts a sample alert (3 real upcoming fixtures). Changes no data |

- Secret **`SLACK_WEBHOOK_URL`** is set. Never print it or commit it.
- Optional repository variable **`ALERT_MIN_DAYS`** (default 5).
- A run takes **about 15-21 minutes**. The collect step times out at 40 min, the job at 50.
- Each run writes **`output/run.log`** and commits it **even if the run fails or times out**.
  It's the way to see what happened, since Actions logs may not be readable from every
  environment.
- The schedule is deliberately **not on the hour**: the original 07:00 run was dropped by
  GitHub on 02/11/2026. Scheduled runs can still start late.

Trigger a run from the CLI: `gh workflow run fixtures.yml -f debug=false`.
Watch it: `gh run list --workflow fixtures.yml` / `gh run view <id>`.

## Code map

```
config/partners.csv        partners, ESPN name variants, group, home/home+away, extra codes, active
fixtures_app/competitions.py  GROUPS: which competitions each group checks (ESPN slugs or tsdb:<id>)
fixtures_app/espn.py       ESPN public feeds (scoreboard, teams, team schedules) + parse_event
fixtures_app/tsdb.py       TheSportsDB (free key "123") for leagues ESPN lacks
fixtures_app/collect.py    per partner: resolve ESPN team id, gather fixtures, keep home (or allowed away), coverage rows
fixtures_app/state.py      data/fixtures.json: remembers fixtures, detects new/changed (date, time, stadium, status)
fixtures_app/history.py    head-to-head from ESPN past-season team schedules -> data/history.json
fixtures_app/timezones.py  local time zone per fixture (country, city overrides, competition fallback)
fixtures_app/excel.py      builds the workbook (About, Upcoming, New & changed, By partner, Coverage, Head-to-head, Past)
fixtures_app/slack.py      Slack Block Kit messages + webhook post
fixtures_app/run.py        entry point: collect -> merge -> flag missing -> head-to-head -> Excel -> Slack
fixtures_app/slack_test.py the Slack test
tests/test_pipeline.py     offline self-test with fake ESPN/TheSportsDB responses
data/                      state committed by the bot: fixtures.json, team_ids.json, history.json (~2 MB)
output/                    fixtures.xlsx and run.log, committed by the bot
```

Local commands:

```bash
pip install -r requirements.txt
python -m tests.test_pipeline              # must print "All checks passed"; run before every push
python -m fixtures_app.run --no-slack      # full run locally (needs internet access to ESPN/TheSportsDB)
```

**The tests read Excel columns by position.** If you add or move columns in `FIXTURE_COLS`
(excel.py), update the indexes in the test, or add new columns at the end.

## Data sources: what we learned the hard way

### ESPN (`site.api.espn.com/apis/site/v2/sports/soccer/...`)
- Undocumented and public; may change without notice.
- **Date-range scoreboards are refused for every league.** After two refusals the code goes
  straight to single days: 60 days, 6 in parallel. Don't "optimise" back to ranges.
- Per-request pause is 0.05 s. 4xx responses aren't retried, and failures are cached per URL.
- Team schedules (`teams/<id>/schedule?fixture=true`) are only fetched for competitions whose
  team list includes the partner. This was a big time saver: 490 partner-competition pairs.
- Match summaries have **no head-to-head section** (checked on 14 competitions). Head-to-head is
  built from `teams/<id>/schedule?season=<year>` for past seasons instead.
- Some competition codes in `competitions.py` are marked *unverified*. The Coverage sheet shows
  "Not available on ESPN" for codes that don't work.
- No Polish or Croatian league. The Swiss and Indonesian leagues are listed but had no fixtures, so
  those come from TheSportsDB.

### TheSportsDB (free key)
- Used for: Cyprus `tsdb:4630`, Croatia `tsdb:4629`, Poland `tsdb:4422`,
  Switzerland `tsdb:4675`, Indonesia `tsdb:4790`. Also Apollon, Dinamo Zagreb, Legia Warsaw,
  Young Boys and Persija league games.
- **Rate limit is the main constraint: roughly 100 requests/hour, with 120 s blocks.**
  Mitigations already in place: 4 s between calls; only rounds from (latest played − 3) to
  +10 ahead; at most 12 min of rate-limit waiting per run, after which the remaining leagues are
  skipped. Fixtures from skipped leagues are kept and **not** flagged as missing.
- Because of the window, the Coverage sheet count for these leagues only covers the next ~10
  rounds. Later fixtures stay in the file from earlier runs.
- **Several runs in a row use up the limit.** Avoid back-to-back manual runs. If it's still a
  problem, the fallback is a paid key (about $9/month) set as a `THESPORTSDB_KEY` secret. The code
  reads that env var, but the workflow doesn't pass it yet.
- `search_all_leagues` only returns 5 leagues per country, so some leagues can't be found that
  way. The Turkish Cup has no source yet.
- The shell sandbox used to build this couldn't reach ESPN or TheSportsDB directly. Lookups were
  done with temporary workflows that committed their output. If your environment has internet
  access, just call the APIs directly.

## Behaviour and rules (where to change them)

- **Home only** by default. Per partner `home+away` with an optional list of competitions
  (`partners.csv`).
- **Slack alert rules**, in `run.py`:
  - `to_alert()`: new fixtures only if **not** a league (`is_league()`: `xxx.N`,
    `bra.camp.*`, `tsdb:*`).
  - Changes only if the note contains a date change, kick-off time change, time confirmed, or a
    postponed/cancelled status. Stadium-only changes are not posted.
  - Everything is filtered by `far_enough()`, which uses `ALERT_MIN_DAYS`.
- **"Not in latest feed"** (orange in Excel) only applies to future fixtures, and not to
  competitions that failed this run or TheSportsDB rounds beyond the fetched window.
- **"Not found on ESPN" warning**: only for partners that rely on ESPN alone. It was a false
  alarm for Legia before this rule.
- **Time zones**: `timezones.py`. Add a city to `CITY_TZ` if a country spans zones (Brazil,
  Indonesia, Canaries, Madeira are covered). All current fixtures resolve.
- **Head-to-head** (`history.py`): `SEASONS_BACK=10`. Past seasons are fetched once and recorded in
  `history["done"]`; the last two seasons are refreshed every run. It only covers the
  competitions configured for the partner, so friendlies and other competitions aren't counted.
  TheSportsDB league fixtures show "No data". The first full fetch took about 5 extra minutes
  (5,291 team-seasons, 20,100 results).
- If head-to-head fails, the run continues and the Excel file is written without it.

## Workflow gotchas

- **Don't push to `main` while a run is in progress if you can avoid it.** The save step
  `git pull --rebase -X theirs` handles it, but a run that started on old code still uses the old
  code.
- Cancelled or failed runs email Carola. Avoid unnecessary runs, and warn her when she might see
  "cancelled" emails.
- Commit messages end with the usual attribution lines. The bot commits as `fixtures-bot`.
- Old files to keep out of the repo: one-off probe workflows. Delete them once used.

## Current status (02/11/2026)

- 543 upcoming home fixtures. 441 have head-to-head, 53 "No meetings since 2016", 49 TheSportsDB.
- The last run succeeded at 14:01 UTC, and all five TheSportsDB leagues refreshed.
- Known gaps:
  - Italy U21 has no upcoming fixtures on ESPN.
  - The Turkish Cup has no source.
  - Young Boys has few Swiss fixtures, because TheSportsDB has published fewer so far.

## Open ideas (not started; ask Carola before doing)

- Show the full list without downloading Excel: either a **weekly Slack overview** of the
  next N weeks, or a **readable page on GitHub** (e.g. a generated `output/fixtures.md`) linked from
  Slack. She was asked which she prefers and hasn't answered yet.
- A paid TheSportsDB key, if rate limits keep skipping leagues.
- Head-to-head from TheSportsDB for its leagues. Limited by the same rate limit.
