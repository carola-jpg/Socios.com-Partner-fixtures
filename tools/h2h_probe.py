"""One-off: can past-season team schedules give head-to-head results?"""
import json, time, requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
H = {"User-Agent": "Mozilla/5.0"}
# (slug, partner team id, opponent name)
cases = [("eng.1", "368", "Coventry"), ("ita.1", "104", "Sassuolo"), ("esp.1", "243", "Alav"),
         ("bra.1", "1936", "Coritiba"), ("tur.1", "432", "Galatasaray"), ("fifa.friendly", "164", "Chile"),
         ("uefa.champions", "432", "Stuttgart")]
out = {}
for slug, tid, opp in cases:
    res = {}
    for season in (2021, 2022, 2023, 2024, 2025):
        url = f"{SITE}/{slug}/teams/{tid}/schedule?season={season}"
        r = requests.get(url, headers=H, timeout=20)
        if not r.ok:
            res[season] = f"HTTP {r.status_code}"; continue
        evs = r.json().get("events") or []
        meets = []
        for e in evs:
            comp = (e.get("competitions") or [{}])[0]
            teams = comp.get("competitors") or []
            names = [t.get("team", {}).get("displayName", "") for t in teams]
            if any(opp.lower() in n.lower() for n in names):
                sc = []
                for t in teams:
                    s = t.get("score")
                    sc.append(f"{t.get('homeAway')}:{t.get('team',{}).get('displayName')}={s.get('displayValue') if isinstance(s, dict) else s}")
                meets.append({"date": e.get("date"), "teams": sc, "status": comp.get("status", {}).get("type", {}).get("name")})
        res[season] = {"events": len(evs), "meetings": meets}
        time.sleep(0.3)
    out[f"{slug}:{tid}:{opp}"] = res
json.dump(out, open("output/h2h_probe.json", "w"), indent=1, ensure_ascii=False)
