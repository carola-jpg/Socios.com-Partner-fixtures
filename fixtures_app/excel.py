"""Write the fixtures workbook."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .timezones import local_and_utc

UK = ZoneInfo("Europe/London")
FONT = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F3864")
NEW_FILL = PatternFill("solid", fgColor="E2EFDA")
CHANGED_FILL = PatternFill("solid", fgColor="FFF2CC")
WARN_FILL = PatternFill("solid", fgColor="FCE4D6")

FIXTURE_COLS = [
    ("Date (local)", 14), ("Day", 6), ("Kick-off (local)", 12), ("Local time zone", 12),
    ("Kick-off (UTC)", 18), ("Time status", 12), ("Partner", 28),
    ("Competition", 28), ("Round", 18), ("Fixture", 42), ("Home/Away", 11), ("Stadium", 30),
    ("City", 16), ("Country", 14), ("Added", 12), ("Last change", 30),
]


def uk_dt(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(UK)


def _fixture_row(r: dict, with_change: bool = True) -> list:
    loc, utc, zone = local_and_utc(r)
    day = loc or utc  # the local date where known, otherwise the UTC date
    timed = bool(utc and r.get("time_confirmed"))
    utc_text = ""
    if timed:
        utc_text = utc.strftime("%H:%M")
        if loc and loc.date() != utc.date():
            utc_text += utc.strftime(" (%d/%m/%Y)")
    added = uk_dt(r.get("first_seen", ""))
    return [
        day.date() if day else None,
        day.strftime("%a") if day else "",
        (loc.strftime("%H:%M") if loc else "unknown") if timed else "TBC",
        zone or ("unknown" if utc else ""),
        utc_text if timed else "TBC",
        "Confirmed" if r.get("time_confirmed") else "TBC",
        r.get("partner", ""),
        r.get("competition", ""),
        r.get("round", ""),
        f"{r.get('home', '')} v {r.get('away', '')}",
        r.get("side", ""),
        r.get("stadium", "") or "TBC",
        r.get("city", ""),
        r.get("country", ""),
        added.date() if added else None,
        r.get("change_note", "") if with_change else "",
    ]


def _sheet(wb, title, cols, rows, fills=None):
    ws = wb.create_sheet(title)
    ws.append([c for c, _ in cols])
    for i, (_, w) in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    for c in ws[1]:
        c.font = Font(name=FONT, bold=True, color="FFFFFF")
        c.fill = HEADER_FILL
        c.alignment = Alignment(vertical="center", wrap_text=True)
    for idx, row in enumerate(rows):
        ws.append(row)
        fill = fills[idx] if fills else None
        for c in ws[ws.max_row]:
            c.font = Font(name=FONT)
            c.alignment = Alignment(vertical="top")
            if fill:
                c.fill = fill
            if isinstance(c.value, datetime) or type(c.value).__name__ == "date":
                c.number_format = "dd/mm/yyyy"
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows) + 1}"
    return ws


def _sort_key(r):
    return (r.get("date_utc") or "9999", r.get("partner", ""))


def write(path: str, state: dict, run_new: list[dict], run_changed: list[dict], coverage: list[dict], run_time: datetime):
    today = run_time.astimezone(UK).date()
    records = sorted(state.values(), key=_sort_key)
    upcoming, past = [], []
    for r in records:
        dt = uk_dt(r.get("date_utc", ""))
        (past if (dt and dt.date() < today) or r.get("completed") else upcoming).append(r)

    new_keys = {(r["event_id"], r["partner"]) for r in run_new}
    changed_keys = {(r["event_id"], r["partner"]) for r in run_changed}

    wb = Workbook()
    wb.remove(wb.active)

    # About
    ws = wb.create_sheet("About")
    lines = [
        ("Partner fixtures", True),
        (f"Updated {run_time.astimezone(UK).strftime('%a %d/%m/%Y, %H:%M')} UK time", False),
        ("", False),
        ("Upcoming: every announced fixture for our partners, earliest first. Green = new this run, yellow = changed this run.", False),
        ("New & changed: everything new or changed since the previous run. Slack only gets new cup, European and international fixtures, and date or kick-off changes, for matches at least 5 days away.", False),
        ("By partner: how many upcoming fixtures each partner has and when the next one is.", False),
        ("Coverage: which competitions were checked for each partner and what was found.", False),
        ("Past: fixtures whose date has gone by.", False),
        ("", False),
        ("Kick-off 'TBC' means the date is announced but the league hasn't fixed the time yet.", False),
        ("Kick-off times are shown in the stadium's local time (with its UTC offset) and in UTC. "
         "Sources: ESPN's public fixture feeds and TheSportsDB.", False),
    ]
    for text, bold in lines:
        ws.append([text])
        ws.cell(ws.max_row, 1).font = Font(name=FONT, bold=bold, size=14 if bold else 11)
    ws.column_dimensions["A"].width = 110

    fills = [NEW_FILL if (r["event_id"], r["partner"]) in new_keys else
             CHANGED_FILL if (r["event_id"], r["partner"]) in changed_keys else
             WARN_FILL if r.get("change_note", "").startswith("Not in latest feed") else None
             for r in upcoming]
    _sheet(wb, "Upcoming", FIXTURE_COLS, [_fixture_row(r) for r in upcoming], fills)

    run_rows = sorted(run_new + run_changed, key=_sort_key)
    ws_nc = _sheet(wb, "New & changed", FIXTURE_COLS, [_fixture_row(r) for r in run_rows],
                   [NEW_FILL if r.get("change_note") == "New" else CHANGED_FILL for r in run_rows])
    if not run_rows:
        ws_nc["A2"] = "No new or changed fixtures since the previous run."
        ws_nc["A2"].font = Font(name=FONT, italic=True, color="808080")

    by_partner = defaultdict(list)
    for r in upcoming:
        by_partner[r["partner"]].append(r)
    partners_seen = sorted({c["partner"] for c in coverage} | set(by_partner))
    rows = []
    for p in partners_seen:
        fx = by_partner.get(p, [])
        nxt = uk_dt(fx[0]["date_utc"]) if fx else None
        comps = sorted({r["competition"] for r in fx})
        rows.append([p, len(fx), sum(1 for r in fx if r["side"] == "Home"),
                     nxt.date() if nxt else None,
                     f"{fx[0]['home']} v {fx[0]['away']}" if fx else "",
                     ", ".join(comps)])
    _sheet(wb, "By partner", [("Partner", 30), ("Upcoming", 10), ("Of which home", 13),
                              ("Next fixture", 13), ("Next match", 40), ("Competitions", 70)], rows)

    cov_rows = [[c["partner"], c["competition"], c["slug"], c["result"]] for c in coverage]
    cov_fills = [WARN_FILL if ("not" in c["result"].lower() and "upcoming" not in c["result"].lower()) else None
                 for c in coverage]
    _sheet(wb, "Coverage", [("Partner", 30), ("Competition", 34), ("Source code", 22), ("Result", 70)],
           cov_rows, cov_fills)

    _sheet(wb, "Past", FIXTURE_COLS, [_fixture_row(r, False) for r in reversed(past)])
    wb.save(path)
    return {"upcoming": len(upcoming), "past": len(past)}
