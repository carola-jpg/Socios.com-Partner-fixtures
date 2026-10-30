"""Read the partner list, find each partner and collect their fixtures (ESPN, plus TheSportsDB where ESPN has gaps)."""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from .competitions import FALLBACK_NAMES, competitions_for
from .espn import ESPN, NotAvailable, parse_event
from .tsdb import TheSportsDB

log = logging.getLogger(__name__)

STOPWORDS = {"fc", "cf", "sc", "ac", "afc", "ssc", "as", "ud", "club", "de", "the", "calcio"}


@dataclass
class Partner:
    name: str
    espn_names: list[str]
    group: str
    fixtures: str  # "home" or "home+away"
    away_competitions: list[str]
    extra_competitions: list[str]
    espn_id: str = ""
    competitions: list[str] = field(default_factory=list)


def _split(v: str, sep: str) -> list[str]:
    return [x.strip() for x in (v or "").split(sep) if x.strip()]


def load_partners(path: str) -> list[Partner]:
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if (row.get("active") or "yes").strip().lower() in ("no", "n", "false", "0"):
                continue
            fx = (row.get("fixtures") or "home").strip().lower().replace(" ", "")
            fx = "home+away" if ("away" in fx) else "home"
            p = Partner(
                name=row["partner"].strip(),
                espn_names=_split(row.get("espn_names", ""), "|") or [row["partner"].strip()],
                group=row["group"].strip(),
                fixtures=fx,
                away_competitions=_split(row.get("away_competitions", ""), ";"),
                extra_competitions=_split(row.get("extra_competitions", ""), ";"),
                espn_id=(row.get("espn_id") or "").strip(),
            )
            p.competitions = competitions_for(p.group, p.extra_competitions)
            out.append(p)
    return out


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return " ".join(t for t in s.split() if t not in STOPWORDS)


def match_team(partner: Partner, teams: list[dict]) -> dict | None:
    wanted = [norm(n) for n in partner.espn_names]
    fields = ("displayName", "name", "shortDisplayName", "location", "nickname")
    # 1) exact match on any name field
    for t in teams:
        names = {norm(t.get(f, "")) for f in fields} - {""}
        if any(w in names for w in wanted):
            return t
    # 2) whole-word containment, only if exactly one team matches
    hits = []
    for t in teams:
        dn = f" {norm(t.get('displayName', ''))} "
        if any(w and f" {w} " in dn for w in wanted):
            hits.append(t)
    return hits[0] if len(hits) == 1 else None


def resolve_partner_id(partner: Partner, espn: ESPN, id_cache: dict) -> str | None:
    if partner.espn_id:
        return partner.espn_id
    if partner.name in id_cache:
        return id_cache[partner.name]
    for slug in partner.competitions:
        if slug.startswith("tsdb:"):
            continue
        try:
            _, teams = espn.league_teams(slug)
        except NotAvailable:
            continue
        t = match_team(partner, teams)
        if t:
            id_cache[partner.name] = str(t["id"])
            log.info("Matched %s -> %s (id %s) in %s", partner.name, t.get("displayName"), t["id"], slug)
            return id_cache[partner.name]
    return None


def name_matches(partner: Partner, team_name: str) -> bool:
    """Exact (normalised) name match, used when we have no ESPN id, e.g. TheSportsDB."""
    n = norm(team_name)
    return bool(n) and any(norm(a) == n for a in partner.espn_names)


class Sources:
    """Fetches each competition once, however many partners play in it."""

    def __init__(self, espn: ESPN, tsdb: TheSportsDB, today: date, days_ahead: int = 400):
        self.espn, self.tsdb = espn, tsdb
        self.start = today - timedelta(days=1)
        self.end = today + timedelta(days=days_ahead)
        self.today = today
        self._events: dict[str, list[dict]] = {}
        self._names: dict[str, str] = {}
        self._errors: dict[str, str] = {}

    def competition(self, slug: str) -> tuple[str, list[dict]] | None:
        """(competition name, parsed events) or None if no source has it."""
        if slug in self._events:
            return self._names[slug], self._events[slug]
        if slug in self._errors:
            return None
        if slug.startswith("tsdb:"):
            try:
                name, events = self.tsdb.league_events(slug[5:], self.today)
            except NotAvailable as e:
                self._errors[slug] = str(e)
                return None
            self._names[slug] = name or FALLBACK_NAMES.get(slug, slug)
            self._events[slug] = events
            return self._names[slug], events
        listed = True
        try:
            lname, _ = self.espn.league_teams(slug)
        except NotAvailable:
            listed, lname = False, None
        try:
            raw = self.espn.scoreboard(slug, self.start, self.end)
        except NotAvailable:
            raw = []
        if not listed and not raw:
            self._errors[slug] = "Not available on ESPN"
            return None
        self._names[slug] = lname or FALLBACK_NAMES.get(slug, slug)
        self._events[slug] = [p for p in (parse_event(e) for e in raw) if p]
        return self._names[slug], self._events[slug]


def collect(partners: list[Partner], espn: ESPN, id_cache: dict, tsdb: TheSportsDB | None = None,
            today: date | None = None) -> tuple[list[dict], list[dict]]:
    today = today or datetime.now(timezone.utc).date()
    src = Sources(espn, tsdb or TheSportsDB(), today)
    fixtures: dict[tuple[str, str], dict] = {}
    coverage: list[dict] = []
    seen_days: set[tuple[str, str]] = set()

    for p in partners:
        pid = resolve_partner_id(p, espn, id_cache)
        home_venue = None
        total = 0
        for slug in p.competitions:
            got = src.competition(slug)
            if got is None:
                where = "TheSportsDB" if slug.startswith("tsdb:") else "ESPN"
                coverage.append({"partner": p.name, "slug": slug,
                                 "competition": FALLBACK_NAMES.get(slug, slug),
                                 "result": f"Not available on {where}"})
                continue
            comp_label, events = got
            events = list(events)
            # The team's own schedule as a second view of the same competition (ESPN only).
            if pid and not slug.startswith("tsdb:"):
                try:
                    events += [x for x in (parse_event(e) for e in espn.team_schedule(slug, pid)) if x]
                except NotAvailable:
                    pass
            kept = 0
            for fx in events:
                fx = dict(fx)
                if fx["completed"] or (fx["date_utc"] or "")[:10] < today.isoformat():
                    continue
                if pid and not slug.startswith("tsdb:"):
                    is_home, is_away = fx["home_id"] == pid, fx["away_id"] == pid
                else:
                    is_home, is_away = name_matches(p, fx["home"]), name_matches(p, fx["away"])
                if not (is_home or is_away):
                    continue
                key = (fx["event_id"], p.name)
                day = (p.name, (fx["date_utc"] or "")[:10])
                # Same match from two sources (or two competitions' feeds): a team plays once a day.
                if key in fixtures or day in seen_days:
                    continue
                side = "Neutral" if fx["neutral"] else ("Home" if is_home else "Away")
                comp_name = fx["league_name"] or comp_label
                if side == "Away" and not _wants_away(p, slug, comp_name):
                    continue
                # National teams move around, so only clubs fall back to their usual ground.
                if not fx["stadium"] and side == "Home" and pid and not p.group.startswith("NAT_"):
                    if home_venue is None:
                        first_espn = next((s for s in p.competitions if not s.startswith("tsdb:")), None)
                        home_venue = espn.team_venue(first_espn, pid) if first_espn else {}
                    fx.update({k: v for k, v in home_venue.items() if v})
                fx.update({"partner": p.name, "side": side, "competition": comp_name, "slug": slug})
                fixtures[key] = fx
                seen_days.add(day)
                kept += 1
            total += kept
            coverage.append({"partner": p.name, "slug": slug, "competition": comp_label,
                             "result": f"{kept} fixture(s)" if kept else "No upcoming fixtures"})
        if not pid and total == 0 and any(not s.startswith("tsdb:") for s in p.competitions):
            coverage.append({"partner": p.name, "slug": "-", "competition": "-",
                             "result": "Team not found on ESPN: add its ESPN id or another name in partners.csv"})
    return list(fixtures.values()), coverage


def _wants_away(p: Partner, slug: str, comp_name: str) -> bool:
    if p.fixtures != "home+away":
        return False
    if not p.away_competitions:
        return True
    names = {norm(x) for x in p.away_competitions}
    return slug in p.away_competitions or norm(comp_name) in names
