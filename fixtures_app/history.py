"""Head-to-head: past results between a partner and its upcoming opponent.

Built from ESPN team schedules for past seasons. A finished season never changes, so each
(competition, team, season) is fetched once and kept in data/history.json; only the last
two seasons are fetched again on every run.
"""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone

from .espn import ESPN, SITE, NotAvailable

log = logging.getLogger(__name__)

SEASONS_BACK = 10  # e.g. from 2016-17 in the 2026-27 season
SHOW_LAST = 5      # meetings summarised in the "H2H last 5" column
SHEET_MAX = 10     # meetings listed per fixture on the Head-to-head sheet


def first_season(today: date) -> int:
    return today.year - SEASONS_BACK


def load(path: str) -> dict:
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("games", {})
        data.setdefault("done", [])
        return data
    return {"games": {}, "done": []}


def save(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data["done"] = sorted(set(data["done"]))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _score(c: dict) -> int | None:
    s = c.get("score")
    if isinstance(s, dict):
        s = s.get("value", s.get("displayValue"))
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return None


def _game(ev: dict, slug: str) -> tuple[str, list] | None:
    """A finished match as (event id, [date, slug, competition, home id, away id, home, away,
    home goals, away goals, shoot-out or ''])."""
    comp = (ev.get("competitions") or [{}])[0] or {}
    status = ((comp.get("status") or ev.get("status") or {}).get("type") or {})
    if not status.get("completed"):
        return None
    sides = {c.get("homeAway"): c for c in comp.get("competitors") or []}
    h, a = sides.get("home"), sides.get("away")
    if not h or not a:
        return None
    hs, as_ = _score(h), _score(a)
    if hs is None or as_ is None:
        return None
    pens = ""
    if h.get("shootoutScore") is not None and a.get("shootoutScore") is not None:
        pens = f"{int(h['shootoutScore'])}-{int(a['shootoutScore'])}"
    league = ev.get("league") or comp.get("league") or {}
    name = league.get("name") or ev.get("seasonType", {}).get("name") or slug
    th, ta = h.get("team") or {}, a.get("team") or {}
    return str(ev.get("id")), [
        (comp.get("date") or ev.get("date") or "")[:10], slug, name,
        str(th.get("id", "")), str(ta.get("id", "")),
        th.get("displayName") or th.get("name") or "", ta.get("displayName") or ta.get("name") or "",
        hs, as_, pens,
    ]


def update(data: dict, partners, id_cache: dict, espn: ESPN, today: date | None = None) -> None:
    """Fetch any missing past seasons, and refresh the last two, for every partner on ESPN."""
    today = today or datetime.now(timezone.utc).date()
    first, last = first_season(today), today.year
    done = set(data["done"])
    jobs = []
    for p in partners:
        tid = p.espn_id or id_cache.get(p.name)
        if not tid:
            continue
        for slug in p.competitions:
            if slug.startswith("tsdb:"):
                continue
            for season in range(first, last + 1):
                key = f"{slug}|{tid}|{season}"
                recent = season >= last - 1  # may still change
                if recent or key not in done:
                    jobs.append((key, slug, tid, season, recent))
    jobs = list({j[0]: j for j in jobs}.values())
    log.info("Head-to-head: %d team seasons to fetch (%d already stored)", len(jobs), len(done))

    def fetch(job):
        key, slug, tid, season, recent = job
        try:
            evs = espn.get(f"{SITE}/{slug}/teams/{tid}/schedule?season={season}").get("events") or []
            return key, recent, evs, slug, True
        except NotAvailable as e:
            # ESPN answering "not found" is final; a network failure is retried next run.
            return key, recent, [], slug, not str(e).startswith("failed after retry")

    added = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        for key, recent, evs, slug, ok in pool.map(fetch, jobs):
            for ev in evs:
                g = _game(ev, slug)
                if g and g[0] not in data["games"]:
                    data["games"][g[0]] = g[1]
                    added += 1
            if not recent and ok:  # a finished season won't change
                done.add(key)
    data["done"] = sorted(done)
    log.info("Head-to-head: %d new past results, %d stored in total", added, len(data["games"]))


def meetings(data: dict, team_id: str, opp_id: str, before: str = "") -> list[dict]:
    """Past results between two ESPN teams, newest first, from `team_id`'s point of view."""
    if not team_id or not opp_id or team_id.startswith("tsdb") or opp_id.startswith("tsdb"):
        return []
    out = []
    for eid, g in data["games"].items():
        day, slug, comp, hid, aid, hname, aname, hs, as_, pens = g
        if {hid, aid} != {team_id, opp_id} or (before and day >= before):
            continue
        mine, theirs = (hs, as_) if hid == team_id else (as_, hs)
        res = "W" if mine > theirs else "L" if mine < theirs else "D"
        score = f"{hname} {hs}-{as_} {aname}" + (f" ({pens} pens)" if pens else "")
        out.append({"date": day, "competition": comp, "score": score, "result": res, "id": eid})
    out.sort(key=lambda m: m["date"], reverse=True)
    return out


def summary(ms: list[dict]) -> str:
    """'W3 D1 L1' (zero counts left out)."""
    if not ms:
        return ""
    n = {k: sum(1 for m in ms if m["result"] == k) for k in "WDL"}
    return " ".join(f"{k}{n[k]}" for k in "WDL" if n[k])


def for_fixture(data: dict, r: dict, today: date, partner_id: str = "") -> dict:
    """H2H columns for one fixture record."""
    if not data["games"]:
        return {"last5": "", "all": "", "last": "", "list": []}
    if str(r.get("event_id", "")).startswith("tsdb"):
        return {"last5": "No data (league from TheSportsDB)", "all": "", "last": "", "list": []}
    if partner_id and str(r.get("away_id")) == partner_id:
        mine, opp = r.get("away_id"), r.get("home_id")
    elif partner_id and str(r.get("home_id")) == partner_id:
        mine, opp = r.get("home_id"), r.get("away_id")
    else:
        mine, opp = ((r.get("home_id"), r.get("away_id")) if r.get("side") != "Away"
                     else (r.get("away_id"), r.get("home_id")))
    ms = meetings(data, str(mine or ""), str(opp or ""), before=(r.get("date_utc") or "")[:10])
    if not ms:
        return {"last5": f"No meetings since {first_season(today)}", "all": "", "last": "", "list": []}
    last = ms[0]
    d = datetime.fromisoformat(last["date"]).strftime("%d/%m/%Y")
    return {
        "last5": summary(ms[:SHOW_LAST]),
        "all": f"{summary(ms)} ({len(ms)} game{'s' if len(ms) != 1 else ''})",
        "last": f"{d} {last['score']}",
        "list": ms[:SHEET_MAX],
    }
