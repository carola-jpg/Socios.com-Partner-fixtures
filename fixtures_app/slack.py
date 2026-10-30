"""Post new and changed fixtures to Slack through an incoming webhook."""

from __future__ import annotations

import logging
from collections import defaultdict

import requests

from .timezones import local_and_utc

log = logging.getLogger(__name__)
MAX_SECTION = 2900  # Slack limit is 3000 characters per section
MAX_BLOCKS = 45  # Slack limit is 50 blocks per message


def _when(r: dict, field: str = "date_utc", timed: bool | None = None) -> str:
    """'Sat 31 Oct 2026, 14:00 local (UTC+1) / 13:00 UTC'."""
    loc, utc, zone = local_and_utc(dict(r, date_utc=r.get(field) or ""))
    if not utc:
        return "date TBC"
    day = loc or utc
    text = day.strftime("%a %d %b %Y")
    if not (r.get("time_confirmed") if timed is None else timed):
        return text + ", time TBC"
    utc_part = utc.strftime("%H:%M UTC")
    if loc and loc.date() != utc.date():
        utc_part += utc.strftime(" (%a %d %b)")
    if loc:
        return f"{text}, {loc.strftime('%H:%M')} local ({zone}) / {utc_part}"
    return f"{text}, {utc_part}"


def _line(r: dict) -> str:
    icon = ":new:" if r.get("change_note") == "New" else ":arrows_counterclockwise:"
    side = "" if r.get("side") == "Home" else f" ({r.get('side')})"
    text = (f"{icon} {r['home']} v {r['away']}{side} · {r.get('competition', '')} · "
            f"{_when(r)} · {r.get('stadium') or 'stadium TBC'}")
    if r.get("change_note") and r.get("change_note") != "New":
        text += f"\n      _{r['change_note']}_"
        if r.get("previous_date_utc") and r.get("previous_date_utc") != r.get("date_utc"):
            text += f" _(was {_when(r, 'previous_date_utc', timed=True)})_"
    return "• " + text


def build_messages(new: list[dict], changed: list[dict], excel_url: str | None, first_run: bool,
                   total: int, partners_missing: list[str]) -> list[dict]:
    footer = []
    if excel_url:
        footer.append({"type": "context", "elements": [
            {"type": "mrkdwn", "text": f":page_facing_up: <{excel_url}|Download the full fixture list (Excel)>"}]})
    if partners_missing:
        footer.append({"type": "context", "elements": [{"type": "mrkdwn", "text":
            ":warning: Not found on ESPN: " + ", ".join(partners_missing) + ". See the Coverage sheet."}]})

    if first_run:
        n_partners = len({r["partner"] for r in new})
        return [{"text": f"Partner fixtures: first load, {total} fixtures", "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": ":soccer: Partner fixtures are set up"}},
            {"type": "section", "text": {"type": "mrkdwn", "text":
                f"First load found *{total} upcoming fixtures* for *{n_partners} partners*. "
                "From now on this channel gets a message every Monday and Friday when new fixtures are "
                "announced or kick-off times, dates or stadiums change."}},
        ] + footer}]

    if not new and not changed:
        return []

    by_partner = defaultdict(list)
    for r in sorted(new + changed, key=lambda r: (r["partner"], r.get("date_utc") or "")):
        by_partner[r["partner"]].append(r)

    title = f":soccer: {len(new)} new fixture{'s' if len(new) != 1 else ''}"
    if changed:
        title += f", {len(changed)} update{'s' if len(changed) != 1 else ''}"
    sections = []
    for partner, rows in by_partner.items():
        chunk = f"*{partner}*"
        for r in rows:
            line = _line(r)
            if len(chunk) + len(line) + 1 > MAX_SECTION:
                sections.append(chunk)
                chunk = f"*{partner}* (cont.)"
            chunk += "\n" + line
        sections.append(chunk)

    messages, blocks = [], [{"type": "header", "text": {"type": "plain_text", "text": title}}]
    for s in sections:
        if len(blocks) >= MAX_BLOCKS:
            messages.append({"text": title, "blocks": blocks})
            blocks = []
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": s}})
    blocks += footer
    messages.append({"text": title, "blocks": blocks})
    return messages


def post(webhook: str, messages: list[dict]) -> None:
    for m in messages:
        r = requests.post(webhook, json=m, timeout=20)
        if r.status_code != 200:
            log.error("Slack returned %s: %s", r.status_code, r.text[:300])
            r.raise_for_status()
