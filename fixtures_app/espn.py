"""Small client for ESPN's free public soccer feeds (no key needed).

The feeds are unofficial, so everything here is defensive: a missing
competition or an unexpected response is logged and skipped rather than
stopping the whole run.
"""

from __future__ import annotations

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Callable

import requests

log = logging.getLogger(__name__)

SITE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
HEADERS = {"User-Agent": "Mozilla/5.0 (partner-fixtures; +https://github.com)"}


class NotAvailable(Exception):
    """ESPN has no data for this competition/team."""


def _http_get(url: str) -> dict:
    """One retry for a network blip or server error; anything ESPN rejects outright
    (4xx) is not retried, because asking again gives the same answer."""
    last = None
    for attempt in range(2):
        try:
            r = requests.get(url, headers=HEADERS, timeout=12)
            if 400 <= r.status_code < 500 and r.status_code != 429:
                raise NotAvailable(f"{r.status_code} for {url}")
            r.raise_for_status()
            return r.json()
        except NotAvailable:
            raise
        except Exception as e:  # network blip, 5xx, 429, bad JSON
            last = e
            if attempt == 0:
                time.sleep(3)
    raise NotAvailable(f"failed after retry: {url} ({last})")


class ESPN:
    def __init__(self, get: Callable[[str], dict] | None = None, delay: float = 0.05, dump_dir: str | None = None):
        self._get = get or _http_get
        self.delay = delay
        self.dump_dir = dump_dir
        self._cache: dict[str, dict] = {}
        self._failed: dict[str, str] = {}
        self.calls = 0
        self.ranges_refused = 0  # competitions where ESPN refused every date range

    def get(self, url: str) -> dict:
        if url in self._cache:
            return self._cache[url]
        if url in self._failed:
            raise NotAvailable(self._failed[url])
        self.calls += 1
        try:
            data = self._get(url)
        except NotAvailable as e:
            self._failed[url] = str(e)
            raise
        if self.delay:
            time.sleep(self.delay)
        self._cache[url] = data
        if self.dump_dir:
            os.makedirs(self.dump_dir, exist_ok=True)
            name = url.replace(SITE, "").strip("/").replace("/", "__").replace("?", "_")[:180]
            with open(os.path.join(self.dump_dir, name + ".json"), "w") as f:
                json.dump(data, f)
        return data

    # ---- leagues & teams -------------------------------------------------
    def league_teams(self, slug: str) -> tuple[str | None, list[dict]]:
        data = self.get(f"{SITE}/{slug}/teams")
        try:
            league = data["sports"][0]["leagues"][0]
        except (KeyError, IndexError, TypeError):
            raise NotAvailable(f"no league data for {slug}")
        teams = [t.get("team", t) for t in league.get("teams", [])]
        if not teams:
            raise NotAvailable(f"no teams listed for {slug}")
        return league.get("name"), teams

    def team_venue(self, slug: str, team_id: str) -> dict:
        """Home stadium from the team's profile (used when a fixture has no venue yet)."""
        try:
            data = self.get(f"{SITE}/{slug}/teams/{team_id}")
        except NotAvailable:
            return {}
        team = data.get("team", {}) or {}
        venue = team.get("venue") or (team.get("franchise") or {}).get("venue") or {}
        return _venue(venue)

    def team_schedule(self, slug: str, team_id: str) -> list[dict]:
        data = self.get(f"{SITE}/{slug}/teams/{team_id}/schedule?fixture=true")
        return data.get("events", []) or []

    def scoreboard(self, slug: str, start: date, end: date, daily_fallback_days: int = 60) -> list[dict]:
        """Every event in a competition between two dates.

        The single-day scoreboard is known to work for soccer. A date range is far
        cheaper, so try that first, then month-sized ranges, then day by day for the
        next few weeks as a last resort.
        """
        fmt = "%Y%m%d"

        def fetch(a: date, b: date) -> list[dict]:
            q = a.strftime(fmt) if a == b else f"{a.strftime(fmt)}-{b.strftime(fmt)}"
            return self.get(f"{SITE}/{slug}/scoreboard?dates={q}&limit=1000").get("events", []) or []

        events: dict[str, dict] = {}
        # ESPN has refused ranges for every league so far; after two refusals, stop asking.
        if self.ranges_refused < 2:
            try:
                return fetch(start, end)
            except NotAvailable:
                log.info("%s: full date range refused, trying month by month", slug)
            try:
                a = start
                while a <= end:
                    b = min(a + timedelta(days=30), end)
                    for ev in fetch(a, b):
                        events[str(ev.get("id"))] = ev
                    a = b + timedelta(days=1)
                return list(events.values())
            except NotAvailable:
                self.ranges_refused += 1
                log.info("%s: month ranges refused, fetching day by day", slug)
        days = [start + timedelta(days=i) for i in range(daily_fallback_days)
                if start + timedelta(days=i) <= end]
        if not days:
            return []

        def one_day(d: date) -> list[dict] | None:
            try:
                return fetch(d, d)
            except NotAvailable:
                return None

        # Probe the first few days; if none work, the competition isn't really there.
        first = [one_day(d) for d in days[:3]]
        if all(r is None for r in first):
            log.info("%s: single days refused too, giving up", slug)
            return []
        with ThreadPoolExecutor(max_workers=6) as pool:
            rest = list(pool.map(one_day, days[3:]))
        for got in first + rest:
            for ev in got or []:
                events[str(ev.get("id"))] = ev
        return list(events.values())


def _venue(v: dict) -> dict:
    v = v or {}
    addr = v.get("address") or {}
    return {
        "stadium": v.get("fullName") or v.get("name") or "",
        "city": addr.get("city") or "",
        "country": addr.get("country") or "",
    }


def parse_event(ev: dict) -> dict | None:
    """Turn an ESPN event into a flat fixture dict, or None if unusable."""
    comps = ev.get("competitions") or [{}]
    comp = comps[0] or {}
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None
    sides = {}
    for c in competitors:
        team = c.get("team") or {}
        sides[c.get("homeAway", "")] = {
            "id": str(team.get("id", "")),
            "name": team.get("displayName") or team.get("name") or team.get("shortDisplayName") or "",
        }
    if "home" not in sides or "away" not in sides:
        return None
    status = (comp.get("status") or ev.get("status") or {}).get("type") or {}
    league = ev.get("league") or comp.get("league") or {}
    return {
        "event_id": str(ev.get("id", "")),
        "date_utc": comp.get("date") or ev.get("date") or "",
        "time_confirmed": comp.get("timeValid", True) is not False,
        "neutral": bool(comp.get("neutralSite")),
        "home_id": sides["home"]["id"],
        "home": sides["home"]["name"],
        "away_id": sides["away"]["id"],
        "away": sides["away"]["name"],
        "round": (comp.get("notes") or [{}])[0].get("headline", "") if comp.get("notes") else "",
        "league_name": league.get("name") or league.get("abbreviation") or "",
        "status": status.get("description") or status.get("name") or "",
        "completed": bool(status.get("completed")),
        **_venue(comp.get("venue") or ev.get("venue") or {}),
    }
