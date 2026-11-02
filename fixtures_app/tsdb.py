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
LOOKBACK_ROUNDS = 3  # catches matches from recent rounds that were moved
AHEAD_ROUNDS = 10    # rounds fetched beyond the latest played one (later rounds are kept from earlier runs)
FINISHED = ("finished", "ft", "aet", "pen", "after")


# Total time the whole run may spend waiting out TheSportsDB rate limits. After that,
# remaining TheSportsDB leagues are skipped for this run (their fixtures are kept as they were).
WAIT_BUDGET = 12 * 60
_waited = 0.0


def _http_get(url: str) -> dict:
    global _waited
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
            if _waited + wait > WAIT_BUDGET:
                raise NotAvailable(f"TheSportsDB rate limit: gave up after waiting {_waited:.0f}s in total")
            log.warning("TheSportsDB rate limit, waiting %ss", wait)
            _waited += wait
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
    def __init__(self, get: Callable[[str], dict] | None = None, key: str | None = None, pause: float = 4.0):
        self._get = get or _http_get
        self.key = key or os.environ.get("THESPORTSDB_KEY", "123")
        self.pause = pause
        self._cache: dict[str, list[dict]] = {}
        self._name: dict[str, str | None] = {}
        self._failed: dict[str, str] = {}
        self.last_round: dict[str, int | None] = {}  # last round fetched, if the scan stopped early

    def _call(self, path: str) -> dict:
        data = self._get(BASE.format(key=self.key) + path)
        if self.pause:
            time.sleep(self.pause)
        return data or {}

    def league_events(self, league_id: str, today: date) -> tuple[str | None, list[dict]]:
        """This season's events from a few rounds before the latest played round onwards."""
        if league_id in self._cache:
            return self._name.get(league_id), self._cache[league_id]
        if league_id in self._failed:
            raise NotAvailable(self._failed[league_id])
        season = season_for(today)
        events: dict[str, dict] = {}
        # Start a few rounds before the latest one played, instead of at round 1: earlier
        # rounds are over, and asking for them used up the free key's rate limit.
        first = 1
        played = [e for e in self._call(f"/eventspastleague.php?id={league_id}").get("events") or []
                  if e.get("strSeason") == season and str(e.get("intRound") or "").isdigit()]
        if played:
            first = max(1, max(int(e["intRound"]) for e in played) - LOOKBACK_ROUNDS)
        empty_streak, found_any = 0, False
        last = first + LOOKBACK_ROUNDS + AHEAD_ROUNDS if played else 60
        for rnd in range(first, last + 1):
            got = self._call(f"/eventsround.php?id={league_id}&r={rnd}&s={season}").get("events") or []
            for ev in got:
                events[str(ev.get("idEvent"))] = ev
            if got:
                found_any, empty_streak = True, 0
            else:
                empty_streak += 1
                if (found_any and empty_streak >= 3) or (not found_any and rnd >= first + LOOKBACK_ROUNDS + 3):
                    break
        # Rounds after `rnd` weren't asked for, so their absence means nothing.
        self.last_round[league_id] = rnd if rnd == last else None
        log.info("TheSportsDB league %s: rounds %d-%d, %d events", league_id, first, rnd, len(events))
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
