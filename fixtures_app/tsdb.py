"""TheSportsDB: free backup source for leagues ESPN doesn't carry (e.g. Cyprus in 2026-27).

Competitions from here are written as "tsdb:<league id>" in competitions.py.
Find a league id at
https://www.thesportsdb.com/api/v1/json/123/search_all_leagues.php?c=<Country>&s=Soccer
(the idLeague field).

The free key "123" is rate limited, so calls are spaced out and 429 responses are
retried after the wait the server asks for.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timezone
from typing import Callable

import requests

from .espn import NotAvailable

log = logging.getLogger(__name__)
BASE = "https://www.thesportsdb.com/api/v1/json/{key}"
FINISHED = ("finished", "ft", "aet", "pen", "after")


def _http_get(url: str) -> dict:
    for attempt in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": "partner-fixtures"}, timeout=20)
        except Exception as e:
            if attempt == 3:
                raise NotAvailable(f"{url}: {e}")
            time.sleep(3 * (attempt + 1))
            continue
        if r.status_code == 429:
            wait = min(int(r.headers.get("Retry-After") or 60), 180)
            log.warning("TheSportsDB rate limit, waiting %ss", wait)
            time.sleep(wait)
            continue
        if r.status_code >= 400:
            raise NotAvailable(f"{r.status_code} for {url}")
        try:
            return r.json() or {}
        except ValueError:
            return {}
    raise NotAvailable(f"rate limited too often: {url}")


def season_for(today: date) -> str:
    """European-style season string, e.g. 2026-2027 from July 2026 to June 2027."""
    y = today.year
    return f"{y}-{y + 1}" if today.month >= 7 else f"{y - 1}-{y}"


class TheSportsDB:
    def __init__(self, get: Callable[[str], dict] | None = None, key: str | None = None, pause: float = 2.0):
        self._get = get or _http_get
        self.key = key or os.environ.get("THESPORTSDB_KEY", "123")
        self.pause = pause
        self._cache: dict[str, list[dict]] = {}
        self._name: dict[str, str | None] = {}
        self._failed: dict[str, str] = {}

    def _call(self, path: str) -> dict:
        data = self._get(BASE.format(key=self.key) + path)
        if self.pause:
            time.sleep(self.pause)
        return data or {}

    def league_events(self, league_id: str, today: date) -> tuple[str | None, list[dict]]:
        """All events this season: the whole-season list (capped on the free key) plus round by round."""
        if league_id in self._cache:
            return self._name.get(league_id), self._cache[league_id]
        if league_id in self._failed:
            raise NotAvailable(self._failed[league_id])
        season = season_for(today)
        events: dict[str, dict] = {}
        for ev in self._call(f"/eventsseason.php?id={league_id}&s={season}").get("events") or []:
            events[str(ev.get("idEvent"))] = ev
        empty_streak, found_any = 0, bool(events)
        for rnd in range(1, 41):
            got = self._call(f"/eventsround.php?id={league_id}&r={rnd}&s={season}").get("events") or []
            for ev in got:
                events[str(ev.get("idEvent"))] = ev
            if got:
                found_any, empty_streak = True, 0
            else:
                empty_streak += 1
                if (found_any and empty_streak >= 3) or (not found_any and rnd >= 3):
                    break
        if not events:
            self._failed[league_id] = f"TheSportsDB has no {season} events for league {league_id}"
            raise NotAvailable(self._failed[league_id])
        parsed = [p for p in (parse_event(e) for e in events.values()) if p]
        name = next((e.get("strLeague") for e in events.values() if e.get("strLeague")), None)
        self._cache[league_id] = parsed
        self._name[league_id] = name
        return name, parsed


def parse_event(ev: dict) -> dict | None:
    home, away = ev.get("strHomeTeam"), ev.get("strAwayTeam")
    if not home or not away:
        return None
    stamp = ev.get("strTimestamp")
    if stamp:
        dt = datetime.fromisoformat(stamp.replace("Z", "").split("+")[0]).replace(tzinfo=timezone.utc)
    elif ev.get("dateEvent"):
        dt = datetime.fromisoformat(ev["dateEvent"]).replace(tzinfo=timezone.utc)
    else:
        return None
    status = ev.get("strStatus") or ""
    time_ok = ev.get("strTime") not in (None, "", "00:00:00")
    return {
        "event_id": f"tsdb{ev.get('idEvent')}",
        "date_utc": dt.strftime("%Y-%m-%dT%H:%MZ"),
        "time_confirmed": time_ok,
        "neutral": False,
        "home_id": f"tsdb{ev.get('idHomeTeam', '')}",
        "home": home,
        "away_id": f"tsdb{ev.get('idAwayTeam', '')}",
        "away": away,
        "round": f"Round {ev['intRound']}" if ev.get("intRound") else "",
        "league_name": ev.get("strLeague") or "",
        "status": status or "Scheduled",
        "completed": any(status.lower().startswith(f) for f in FINISHED),
        "stadium": ev.get("strVenue") or "",
        "city": ev.get("strCity") or "",
        "country": ev.get("strCountry") or "",
    }
