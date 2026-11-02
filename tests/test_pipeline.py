"""End-to-end test with fake ESPN responses. Run: python -m tests.test_pipeline"""

import os
import shutil
import tempfile
from datetime import datetime, timezone

from openpyxl import load_workbook

from fixtures_app import run, slack
from fixtures_app.espn import ESPN, SITE, NotAvailable
from fixtures_app.tsdb import TheSportsDB


def team(i, name, **kw):
    return {"team": {"id": str(i), "displayName": name, "name": name, **kw}}


def event(eid, date, home, away, venue=None, time_valid=True, league=None, status="Scheduled"):
    comp = {
        "date": date, "timeValid": time_valid,
        "competitors": [
            {"homeAway": "home", "team": {"id": str(home[0]), "displayName": home[1]}},
            {"homeAway": "away", "team": {"id": str(away[0]), "displayName": away[1]}},
        ],
        "status": {"type": {"description": status, "completed": False}},
    }
    if venue:
        comp["venue"] = {"fullName": venue[0], "address": {"city": venue[1], "country": venue[2]}}
    ev = {"id": str(eid), "date": date, "competitions": [comp]}
    if league:
        ev["league"] = {"name": league}
    return ev


MILAN, INTER, JUVE, ROMA = (103, "AC Milan"), (110, "Internazionale"), (111, "Juventus"), (104, "AS Roma")
ARSENAL, SPURS = (359, "Arsenal"), (367, "Tottenham Hotspur")
ITALY, SPAIN = (162, "Italy"), (164, "Spain")
SAN_SIRO = ("San Siro", "Milan", "Italy")


def make_responses(second_run=False):
    r = {
        f"{SITE}/ita.1/teams": {"sports": [{"leagues": [{"name": "Italian Serie A", "teams": [
            team(*MILAN), team(*INTER), team(*JUVE), team(*ROMA)]}]}]},
        f"{SITE}/ita.1/teams/103": {"team": {"venue": {"fullName": "San Siro", "address": {"city": "Milan", "country": "Italy"}}}},
        f"{SITE}/ita.1/teams/103/schedule?fixture=true": {"events": [
            event(1, "2026-12-13T19:45Z" if second_run else "2026-12-06T19:45Z", MILAN, JUVE, SAN_SIRO),
            event(2, "2026-11-22T17:00Z", INTER, MILAN, ("San Siro", "Milan", "Italy")),
            event(3, "2027-01-10T14:00Z", MILAN, ROMA, None, time_valid=second_run),
        ] + ([event(4, "2027-02-01T19:45Z", MILAN, INTER, SAN_SIRO)] if second_run else [])},
        f"{SITE}/ita.1/teams/110/schedule?fixture=true": {"events": [
            event(2, "2026-11-22T17:00Z", INTER, MILAN, ("San Siro", "Milan", "Italy"))]},
        f"{SITE}/uefa.champions/teams": {"sports": [{"leagues": [{"name": "UEFA Champions League", "teams": [
            team(*MILAN), team(*ARSENAL)]}]}]},
        f"{SITE}/uefa.champions/teams/103/schedule?fixture=true": {"events": [
            event(10, "2026-11-25T20:00Z", MILAN, (132, "Bayern Munich"), SAN_SIRO, league="UEFA Champions League")]},
        f"{SITE}/eng.1/teams": {"sports": [{"leagues": [{"name": "English Premier League", "teams": [
            team(*ARSENAL), team(*SPURS)]}]}]},
        # Arsenal only appears in the league-wide scoreboard, not the team schedule
        "SCOREBOARD:eng.1": {"events": (
            [] if second_run else [event(20, "2026-11-29T16:30Z", ARSENAL, SPURS, ("Emirates Stadium", "London", "England"))])},
        f"{SITE}/fifa.friendly/teams": {"sports": [{"leagues": [{"name": "International Friendly", "teams": [
            team(*ITALY), team(*SPAIN)]}]}]},
        "SCOREBOARD:fifa.friendly": {"events": [
            event(30, "2027-03-26T19:45Z", ITALY, SPAIN, ("Stadio Olimpico", "Rome", "Italy"))]},
    }
    # Everything not listed above behaves like a competition ESPN doesn't have
    return r


def fake_get(responses):
    def get(url):
        if "/scoreboard?" in url:
            slug = url.split("/soccer/")[1].split("/")[0]
            dates = url.split("dates=")[1].split("&")[0]
            if slug == "fifa.friendly" and "-" in dates:
                a, b = dates.split("-")
                if int(b[:6]) - int(a[:6]) > 1 and int(b[:4]) * 12 + int(b[4:6]) - int(a[:4]) * 12 - int(a[4:6]) > 1:
                    raise NotAvailable("range too long")  # forces the month-by-month fallback
            return responses.get(f"SCOREBOARD:{slug}", {"events": []})
        if url in responses:
            return responses[url]
        if url.endswith("/teams"):
            raise NotAvailable(url)
        return {"events": []}
    return get


def main():
    tmp = tempfile.mkdtemp()
    partners_csv = os.path.join(tmp, "partners.csv")
    with open(partners_csv, "w") as f:
        f.write("partner,espn_names,group,fixtures,away_competitions,extra_competitions,espn_id,active\n"
                "AC Milan,AC Milan|Milan,ITA,home,,,,yes\n"
                "FC Inter,Internazionale|Inter,ITA,home,,,,yes\n"
                "Arsenal,Arsenal,ENG,home+away,,,,yes\n"
                "FIGC (Italy) (Men's Team),Italy,NAT_UEFA_MEN,home,,,,yes\n"
                "Imaginary FC,Imaginary,ITA,home,,,,yes\n"
                "Apollon,Apollon Limassol|Apollon,CYP,home,,,,yes\n")

    def tsdb_get(url):
        if "eventspastleague" in url and "id=4630" in url:
            return {"events": [{"idEvent": "8999", "strSeason": "2026-2027", "intRound": "10",
                                "strHomeTeam": "Omonia Nicosia", "strAwayTeam": "Apollon Limassol"}]}
        if "eventsround" in url and "id=4630" in url and "r=6&" in url:
            raise AssertionError("rounds before 7 should be skipped (latest played 10, look back 3)")
        if "eventsround" in url and "id=4630" in url and "r=11&" in url:
            return {"events": [
                {"idEvent": "9001", "strHomeTeam": "Apollon Limassol", "strAwayTeam": "Omonia Nicosia",
                 "idHomeTeam": "1", "idAwayTeam": "2", "strTimestamp": "2026-11-21T17:00:00",
                 "strTime": "17:00:00", "strVenue": "Alphamega Stadium", "strStatus": "Not Started",
                 "intRound": "11", "strLeague": "Cypriot First Division"},
                {"idEvent": "9002", "strHomeTeam": "Pafos", "strAwayTeam": "Apollon Limassol",
                 "idHomeTeam": "3", "idAwayTeam": "1", "strTimestamp": "2026-11-28T17:00:00",
                 "strTime": "00:00:00", "strStatus": "Not Started", "strLeague": "Cypriot First Division"},
            ]}
        return {"events": None}
    fake_tsdb = lambda: TheSportsDB(get=tsdb_get, pause=0)
    run.PARTNERS = partners_csv
    run.STATE = os.path.join(tmp, "data", "fixtures.json")
    run.IDS = os.path.join(tmp, "data", "team_ids.json")
    run.HISTORY = os.path.join(tmp, "data", "history.json")
    run.EXCEL = os.path.join(tmp, "output", "fixtures.xlsx")
    os.environ["EXCEL_URL"] = "https://example.com/fixtures.xlsx"

    sent = []
    slack.post = lambda hook, msgs: sent.append(msgs)
    os.environ["SLACK_WEBHOOK_URL"] = "https://hooks.slack.test/x"

    # Run 1: first load
    rc = run.main([], espn=ESPN(get=fake_get(make_responses()), delay=0), tsdb=fake_tsdb(),
                  now=datetime(2026, 11, 2, 7, tzinfo=timezone.utc))
    assert rc == 0
    assert "first load" in sent[-1][0]["text"], sent[-1]
    wb = load_workbook(run.EXCEL)
    up = list(wb["Upcoming"].iter_rows(min_row=2, values_only=True))
    fixtures = {(r[6], r[9]) for r in up}
    print("Run 1 upcoming:", *sorted(fixtures), sep="\n  ")
    assert ("AC Milan", "AC Milan v Juventus") in fixtures
    assert ("AC Milan", "AC Milan v Bayern Munich") in fixtures
    assert ("FC Inter", "Internazionale v AC Milan") in fixtures      # Inter's home game
    assert ("AC Milan", "Internazionale v AC Milan") not in fixtures  # Milan away: excluded
    assert ("Arsenal", "Arsenal v Tottenham Hotspur") in fixtures
    assert ("FIGC (Italy) (Men's Team)", "Italy v Spain") in fixtures   # via month-by-month fallback
    assert ("Apollon", "Apollon Limassol v Omonia Nicosia") in fixtures  # via TheSportsDB
    assert ("Apollon", "Pafos v Apollon Limassol") not in fixtures       # away, excluded
    assert sum(1 for f in fixtures if f[1] == "Italy v Spain") == 1
    roma = [r for r in up if r[9] == "AC Milan v Roma" or r[9] == "AC Milan v AS Roma"][0]
    assert roma[2] == "TBC" and roma[4] == "TBC" and roma[11] == "San Siro", roma  # time TBC, stadium from team profile
    timed = [r for r in up if r[2] not in ("TBC", None)]
    assert timed and all(r[3].startswith("UTC") and r[4] not in ("TBC", "", None) for r in timed), timed[:3]
    cov = list(wb["Coverage"].iter_rows(min_row=2, values_only=True))
    assert any(c[0] == "Imaginary FC" and "not found" in c[3] for c in cov)
    assert any(c[2] == "cro.1" for c in cov) is False  # only ITA/ENG/NAT groups here

    # Run 2: one new, one moved, one time confirmed, Arsenal fixture disappears
    rc = run.main([], espn=ESPN(get=fake_get(make_responses(second_run=True)), delay=0), tsdb=fake_tsdb(),
                  now=datetime(2026, 11, 6, 7, tzinfo=timezone.utc))
    assert rc == 0
    msg = sent[-1][0]
    body = "\n".join(b["text"]["text"] for b in msg["blocks"] if b["type"] == "section")
    print("\nRun 2 Slack title:", msg["text"])
    print(body)
    # The new fixture is a league match, so it's in Excel but not in Slack.
    assert msg["text"] == ":soccer: 2 date/time changes", msg["text"]
    assert "AC Milan v Internazionale" not in body
    assert "Date changed" in body and "Kick-off time confirmed" in body
    wb = load_workbook(run.EXCEL)
    up = list(wb["Upcoming"].iter_rows(min_row=2, values_only=True))
    ars = [r for r in up if r[6] == "Arsenal"][0]
    assert ars[15].startswith("Not in latest feed"), ars
    nc = list(wb["New & changed"].iter_rows(min_row=2, values_only=True))
    assert len(nc) == 3, nc

    # Run 3: nothing changed -> no Slack message
    n = len(sent)
    run.main([], espn=ESPN(get=fake_get(make_responses(second_run=True)), delay=0), tsdb=fake_tsdb(),
             now=datetime(2026, 11, 9, 7, tzinfo=timezone.utc))
    assert len(sent) == n, "should not post when nothing changed"

    # Run 4: ESPN outage -> keep data, warn
    rc = run.main([], espn=ESPN(get=lambda u: (_ for _ in ()).throw(NotAvailable(u)), delay=0),
                  tsdb=TheSportsDB(get=lambda u: {}, pause=0),
                  now=datetime(2026, 11, 13, 7, tzinfo=timezone.utc))
    assert rc == 1 and "no data" in sent[-1][0]["text"]

    sample_out = os.environ.get("SAMPLE_XLSX")
    if sample_out:
        shutil.copy(os.path.join(tmp, "output", "fixtures.xlsx"), sample_out)
    print("\nAll checks passed")


def test_alert_rules():
    now = datetime(2026, 11, 2, 7, tzinfo=timezone.utc)
    later = "2026-12-01T19:45Z"
    added = [{"slug": "ita.1", "date_utc": later}, {"slug": "ita.coppa_italia", "date_utc": later},
             {"slug": "uefa.champions", "date_utc": later}, {"slug": "fifa.friendly", "date_utc": later},
             {"slug": "tsdb:4422", "date_utc": later}, {"slug": "bra.camp.paulista", "date_utc": later},
             {"slug": "eng.fa", "date_utc": "2026-11-04T19:45Z"}]  # cup, but only 2 days away
    changed = [{"slug": "ita.1", "date_utc": later, "change_note": "Kick-off time changed"},
               {"slug": "ita.1", "date_utc": later, "change_note": "Stadium changed"},
               {"slug": "tsdb:4629", "date_utc": later, "change_note": "Date changed"},
               {"slug": "eng.1", "date_utc": later, "change_note": "Status: Postponed"}]
    new, moved = run.to_alert(added, changed, now)
    assert [r["slug"] for r in new] == ["ita.coppa_italia", "uefa.champions", "fifa.friendly"], new
    assert [r["change_note"] for r in moved] == ["Kick-off time changed", "Date changed", "Status: Postponed"]


def test_head_to_head():
    from datetime import date
    from fixtures_app import history

    def ev(eid, day, hid, hname, hs, aid, aname, as_, pens=None):
        comp = {"date": day + "T19:45Z", "status": {"type": {"completed": True}}, "competitors": [
            {"homeAway": "home", "team": {"id": hid, "displayName": hname}, "score": {"value": hs, "displayValue": str(hs)},
             **({"shootoutScore": pens[0]} if pens else {})},
            {"homeAway": "away", "team": {"id": aid, "displayName": aname}, "score": {"value": as_, "displayValue": str(as_)},
             **({"shootoutScore": pens[1]} if pens else {})}]}
        return {"id": eid, "date": comp["date"], "league": {"name": "Italian Serie A"}, "competitions": [comp]}

    sched = {"events": [
        ev("1", "2025-10-26", "2", "Sassuolo", 0, "1", "AS Roma", 1),
        ev("2", "2026-01-10", "1", "AS Roma", 2, "2", "Sassuolo", 0),
        ev("3", "2023-03-12", "1", "AS Roma", 3, "2", "Sassuolo", 4),
        ev("4", "2024-01-20", "1", "AS Roma", 1, "2", "Sassuolo", 1, pens=(4, 3)),
        ev("5", "2024-02-01", "1", "AS Roma", 1, "3", "Napoli", 1),
        {"id": "6", "competitions": [{"status": {"type": {"completed": False}}, "competitors": []}]},
    ]}

    class FakeESPN:
        def get(self, url):
            if "season=2025" in url and "ita.1" in url:
                return sched
            return {"events": []}

    class P:
        name, espn_id, competitions = "AS Roma", "1", ["ita.1", "tsdb:1"]

    data = {"games": {}, "done": []}
    history.update(data, [P()], {}, FakeESPN(), date(2026, 11, 2))
    assert len(data["games"]) == 5, data["games"]
    assert "ita.1|1|2016" in data["done"] and "ita.1|1|2026" not in data["done"]  # current season refetched
    fx = {"event_id": "99", "partner": "AS Roma", "home_id": "1", "away_id": "2", "side": "Home",
          "date_utc": "2026-11-29T14:00Z"}
    info = history.for_fixture(data, fx, date(2026, 11, 2), "1")
    assert info["last5"] == "W2 D1 L1", info
    assert info["last"] == "10/01/2026 AS Roma 2-0 Sassuolo", info
    assert any("(4-3 pens)" in m["score"] for m in info["list"]), info["list"]
    away = dict(fx, home_id="2", away_id="1", side="Away")
    assert history.for_fixture(data, away, date(2026, 11, 2), "1")["last5"] == "W2 D1 L1"
    none = dict(fx, away_id="77")
    assert history.for_fixture(data, none, date(2026, 11, 2), "1")["last5"] == "No meetings since 2016"
    assert history.for_fixture(data, dict(fx, event_id="tsdb5"), date(2026, 11, 2), "1")["last5"].startswith("No data")


def test_alert_window():
    now = datetime(2026, 11, 2, 7, tzinfo=timezone.utc)
    assert not run.far_enough({"date_utc": "2026-11-04T19:45Z"}, now, 5)   # 2 days away
    assert not run.far_enough({"date_utc": "2026-11-07T06:59Z"}, now, 5)   # just under 5 days
    assert run.far_enough({"date_utc": "2026-11-07T07:00Z"}, now, 5)       # exactly 5 days
    assert run.far_enough({"date_utc": ""}, now, 5)                        # date not set yet


if __name__ == "__main__":
    test_alert_window()
    test_alert_rules()
    test_head_to_head()
    main()
