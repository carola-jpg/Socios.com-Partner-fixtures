"""One-off: find TheSportsDB league ids for competitions ESPN doesn't cover."""
import json, time, datetime, requests

B = "https://www.thesportsdb.com/api/v1/json/123"
today = datetime.date.today().isoformat()

def get(path):
    for _ in range(4):
        r = requests.get(B + path, timeout=20)
        if r.status_code == 429:
            time.sleep(20); continue
        time.sleep(2.5)
        try:
            return r.json() or {}
        except Exception:
            return {}
    return {}

out = []
for country in ["Poland", "Croatia", "Switzerland", "Indonesia", "Turkey"]:
    leagues = get(f"/search_all_leagues.php?c={country}&s=Soccer").get("countries") or []
    out.append(f"== {country}: {len(leagues)} leagues")
    for lg in leagues:
        lid, name, season = lg.get("idLeague"), lg.get("strLeague"), lg.get("strCurrentSeason")
        evs = []
        for s in [season, "2026-2027", "2026"]:
            if not s: continue
            evs = get(f"/eventsseason.php?id={lid}&s={s}").get("events") or []
            if evs: season = s; break
        upcoming = [e for e in evs if (e.get("dateEvent") or "") >= today]
        teams = sorted({e.get("strHomeTeam") for e in evs if e.get("strHomeTeam")})
        out.append(f"{lid}\t{name}\tseason={season}\tevents={len(evs)}\tupcoming={len(upcoming)}\tfirst_upcoming={min((e.get('dateEvent') for e in upcoming), default='-')}")
        out.append("    teams: " + ", ".join(teams[:30]))
open("output/tsdb_lookup.txt", "w").write("\n".join(out) + "\n")
print("\n".join(out))
