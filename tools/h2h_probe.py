"""One-off: see what head-to-head data ESPN's match summary has."""
import json, time, requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
H = {"User-Agent": "Mozilla/5.0"}
pick = json.load(open("tools/h2h_pick.json"))
out = {}
for slug, (eid, home, away) in pick.items():
    r = requests.get(f"{SITE}/{slug}/summary?event={eid}", headers=H, timeout=20)
    info = {"status": r.status_code, "match": f"{home} v {away}"}
    if r.ok:
        j = r.json()
        info["top_keys"] = sorted(j.keys())
        h2h = j.get("headToHeadGames")
        info["h2h_type"] = type(h2h).__name__
        if isinstance(h2h, list):
            info["h2h_len"] = len(h2h)
            info["h2h_sample"] = json.dumps(h2h[:1])[:2500]
            games = []
            for block in h2h:
                for e in block.get("events", []) or []:
                    games.append({k: e.get(k) for k in ("gameDate", "score", "homeTeamScore", "awayTeamScore",
                                  "homeTeamId", "awayTeamId", "gameResult", "leagueName", "leagueAbbreviation",
                                  "competitors", "atVs", "opponent")})
            info["h2h_games"] = games[:8]
        # other possibly useful sections
        for k in ("lastFiveGames", "boxscore", "standings", "gameInfo", "odds"):
            if k in j:
                info[f"has_{k}"] = True
        lf = j.get("lastFiveGames")
        if lf:
            info["lastFive_sample"] = json.dumps(lf[:1])[:800]
    out[slug] = info
    time.sleep(0.5)
json.dump(out, open("output/h2h_probe.json", "w"), indent=1, ensure_ascii=False)
print(json.dumps({k: (v.get("status"), v.get("h2h_type"), v.get("h2h_len"), len(v.get("h2h_games") or [])) for k, v in out.items()}, indent=1))
