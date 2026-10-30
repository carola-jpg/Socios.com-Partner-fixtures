# Partner fixtures

Every Monday and Friday morning this collects the fixtures for our partner clubs and
national teams across leagues, cups, European/South American/Asian competitions and
international matches. It then:

- updates **`output/fixtures.xlsx`** (download it from this repo), and
- posts to **Slack** when new fixtures are announced or a date, kick-off time or
  stadium changes, for matches at least **5 days away** (closer matches are only in
  the Excel file; change the number with an `ALERT_MIN_DAYS` repository variable).

By default only **home** fixtures are kept. Cup and European matches turn up
automatically once a team has qualified or been drawn, as do play-offs and other later
rounds.

Data comes from free sources, so there's no API key and nothing to pay:

- **ESPN's public fixture feeds** cover almost everything. Each competition is fetched
  once as a whole (the league "scoreboard"), and each team's own schedule is used as a
  cross-check.
- **TheSportsDB** covers what ESPN is missing: currently the Cypriot First Division,
  because ESPN has no 2026-27 Cypriot season.

GitHub Actions runs it for free.

---

## One-time setup (about 15 minutes)

### 1. Create the Slack webhook
1. Go to <https://api.slack.com/apps> → **Create New App** → **From scratch**. Name it
   e.g. "Partner fixtures" and pick your workspace.
2. In the left menu open **Incoming Webhooks** and switch it **On**.
3. Click **Add New Webhook to Workspace**, choose the channel for the alerts, then
   click **Allow**.
4. Copy the webhook URL (it starts with `https://hooks.slack.com/services/...`). Keep it
   private: anyone who has it can post to that channel.

### 2. Add the webhook to GitHub
In this repo: **Settings → Secrets and variables → Actions → New repository secret**
- Name: `SLACK_WEBHOOK_URL`
- Secret: paste the webhook URL

### 3. Run it for the first time
1. Open the **Actions** tab. If GitHub asks, click to enable workflows.
2. Choose **Partner fixtures** → **Run workflow**. Tick *debug* for the first run, then
   click **Run workflow**.
3. After a few minutes Slack gets a "Partner fixtures are set up" message, and
   `output/fixtures.xlsx` appears in the repo.

After that it runs by itself every **Monday and Friday at 07:00 UTC** (07:00 UK time in
winter, 08:00 in summer). You can also run it any time with **Run workflow**.

---

## The Excel file

| Sheet | What's on it |
|---|---|
| About | When it was last updated, and a key to the colours |
| Upcoming | Every announced fixture, earliest first, with kick-off in local time and UTC. Green = new this run, yellow = changed, orange = no longer in the feed (check it) |
| New & changed | Only what changed in the latest run. Slack got the same list, minus matches less than 5 days away |
| By partner | Number of upcoming fixtures and the next match for each partner |
| Coverage | Which competitions were checked for each partner and what was found |
| Past | Fixtures whose date has passed |

**Kick-off "TBC"** means the date is announced but the league hasn't set the time yet.
When the time is confirmed, you get a Slack update.

To download it, open `output/fixtures.xlsx` in the repo and click **Download raw file**.
The link at the bottom of each Slack message points to the same file.

---

## Changing partners or settings

Everything is in **`config/partners.csv`**. Open it in GitHub, click the pencil icon,
edit, then click **Commit changes**. The next run picks it up.

| Column | What it does |
|---|---|
| `partner` | Our name for the partner, as shown in Excel and Slack |
| `espn_names` | Names ESPN might use for the team, separated by `\|` |
| `group` | Which competitions to check, e.g. `ITA`, `ENG`, `BRA`, `NAT_UEFA_MEN` (see `fixtures_app/competitions.py`) |
| `fixtures` | `home` (default) or `home+away` |
| `away_competitions` | With `home+away`: which competitions to keep away games for, separated by `;` (ESPN codes like `uefa.champions` or names like `Coppa Italia`). Leave it empty to keep away games in every competition |
| `extra_competitions` | Extra ESPN codes for this partner only, separated by `;` |
| `espn_id` | Only needed if the team isn't found automatically (see Coverage) |
| `active` | `no` pauses a partner without deleting the row |

**Example:** Juventus also gives you away tickets for the Champions League and Coppa Italia:

```
Juventus,Juventus,ITA,home+away,uefa.champions;ita.coppa_italia,,,yes
```

**Adding a partner:** add a row and pick the group that matches its country. If its
league isn't covered by any group yet, add the group in `fixtures_app/competitions.py`.

**Finding competition codes:**
- **ESPN:** look up the `slug` field at
  <https://site.api.espn.com/apis/site/v2/leagues/dropdown?sport=soccer&limit=500>. To
  check one, open `https://site.api.espn.com/apis/site/v2/sports/soccer/<slug>/scoreboard`.
- **TheSportsDB:** look up the `idLeague` at
  <https://www.thesportsdb.com/api/v1/json/123/search_all_leagues.php?c=Cyprus&s=Soccer>
  (change the country), then add it as `tsdb:<id>`. Use this when ESPN shows
  "Not available" on the Coverage sheet.

Esports, MMA, rugby and motorsport partners aren't included on purpose.

---

## Good to know

- **The data sources are unofficial or free-tier.** ESPN's feeds are public but
  undocumented, so ESPN could change them without notice. TheSportsDB's free key is rate
  limited, so the run waits between calls, which adds a minute or two. If a run gets no data at all, the previous data is
  kept and Slack gets a warning instead.
- **Some competition codes are best guesses.** These are marked "unverified" in
  `competitions.py`, e.g. the Croatian, Polish and Swiss leagues, the Turkish cup and the
  Brazilian state championships. If ESPN doesn't have one, it shows as "Not available on
  ESPN" on the Coverage sheet and the rest of the run carries on.
- **Women's and U21 coverage** depends on what ESPN lists. Check the Coverage sheet for
  those partners after the first run.
- **"Not in latest feed"** means a fixture we had before is no longer listed. It may have
  been postponed or rescheduled, so check it on the club's site.

## Running it on your own computer (optional)

```bash
pip install -r requirements.txt
python -m fixtures_app.run --no-slack      # updates output/fixtures.xlsx only
python -m tests.test_pipeline              # self-test with sample data
```
