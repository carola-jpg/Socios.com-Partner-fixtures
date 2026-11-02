"""Entry point: python -m fixtures_app.run"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone

from . import excel, slack, state
from .collect import collect, load_partners
from .espn import ESPN
from .tsdb import TheSportsDB

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTNERS = os.path.join(ROOT, "config", "partners.csv")
STATE = os.path.join(ROOT, "data", "fixtures.json")
IDS = os.path.join(ROOT, "data", "team_ids.json")
EXCEL = os.path.join(ROOT, "output", "fixtures.xlsx")

log = logging.getLogger("fixtures")

# Slack only mentions matches at least this many days away (the Excel file still lists all).
ALERT_MIN_DAYS = int(os.environ.get("ALERT_MIN_DAYS") or 5)


# Which changes are worth a Slack message.
ALERT_CHANGES = ("Date changed", "Kick-off time changed", "Kick-off time confirmed", "Status:")


def is_league(slug: str) -> bool:
    """League competitions (e.g. ita.1, eng.2, bra.camp.paulista, TheSportsDB leagues),
    as opposed to cups, European competitions and internationals."""
    slug = slug or ""
    return bool(re.fullmatch(r"[a-z]{3}\.\d", slug)) or slug.startswith(("bra.camp.", "tsdb:"))


def to_alert(added: list[dict], changed: list[dict], now: datetime) -> tuple[list[dict], list[dict]]:
    """New cup/European/international fixtures, plus date or kick-off changes in any
    competition, for matches at least ALERT_MIN_DAYS away."""
    new = [r for r in added if not is_league(r.get("slug", "")) and far_enough(r, now)]
    moved = [r for r in changed
             if any(n in (r.get("change_note") or "") for n in ALERT_CHANGES) and far_enough(r, now)]
    return new, moved


def far_enough(r: dict, now: datetime, days: int = ALERT_MIN_DAYS) -> bool:
    """True if the match is at least `days` days after `now`, or has no date yet."""
    iso = r.get("date_utc") or ""
    if not iso:
        return True
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return True
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= now + timedelta(days=days)


def excel_url() -> str | None:
    if os.environ.get("EXCEL_URL"):
        return os.environ["EXCEL_URL"]
    server, repo = os.environ.get("GITHUB_SERVER_URL"), os.environ.get("GITHUB_REPOSITORY")
    if server and repo:
        branch = os.environ.get("GITHUB_REF_NAME", "main")
        return f"{server}/{repo}/raw/{branch}/output/fixtures.xlsx"
    return None


def main(argv=None, espn: ESPN | None = None, now: datetime | None = None,
         tsdb: TheSportsDB | None = None) -> int:
    ap = argparse.ArgumentParser(description="Collect partner fixtures, update Excel, notify Slack")
    ap.add_argument("--no-slack", action="store_true", help="don't post to Slack")
    ap.add_argument("--dump", metavar="DIR", help="save raw ESPN responses here (for debugging)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    now = now or datetime.now(timezone.utc)
    partners = load_partners(PARTNERS)
    id_cache = state.load(IDS)
    espn = espn or ESPN(dump_dir=args.dump)

    log.info("Checking %d partners", len(partners))
    fetched, coverage = collect(partners, espn, id_cache, tsdb=tsdb, today=now.date())
    old = state.load(STATE)
    first_run = not old
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")

    # Guard against an ESPN outage wiping everything: if nothing came back, change nothing.
    if not fetched and old:
        log.error("ESPN returned no fixtures at all; keeping the previous data unchanged.")
        if webhook and not args.no_slack:
            slack.post(webhook, [{"text": ":warning: Partner fixtures: ESPN returned no data this run, "
                                          "so nothing was updated. It will try again at the next run."}])
        return 1

    new_state, added, changed = state.merge(old, fetched, now)

    # Future fixtures we knew about but that weren't in today's feed: flag them for a manual check.
    seen = {state.key(f) for f in fetched}
    # A competition that couldn't be fetched this run says nothing about its fixtures.
    failed = {c["slug"] for c in coverage if c["result"].startswith("Not available")}
    # TheSportsDB leagues are only read a few rounds ahead; later rounds weren't checked.
    last_round = {c["slug"]: c["last_round"] for c in coverage if c.get("last_round")}
    for k, rec in new_state.items():
        if k in seen or rec.get("slug") in failed:
            continue
        rnd = (rec.get("round") or "").replace("Round ", "")
        if rec.get("slug") in last_round and rnd.isdigit() and int(rnd) > last_round[rec["slug"]]:
            continue
        dt = excel.uk_dt(rec.get("date_utc", ""))
        if dt and dt >= now and not rec.get("change_note", "").startswith("Not in latest feed"):
            rec["change_note"] = "Not in latest feed – may have moved or been cancelled, please check"

    state.save(STATE, new_state)
    state.save(IDS, id_cache)
    os.makedirs(os.path.dirname(EXCEL), exist_ok=True)
    counts = excel.write(EXCEL, new_state, added, changed, coverage, now)
    log.info("New: %d, changed: %d, upcoming: %d, past: %d", len(added), len(changed),
             counts["upcoming"], counts["past"])

    missing = sorted({c["partner"] for c in coverage if c["result"].startswith("Team not found")})
    alert_new, alert_changed = to_alert(added, changed, now)
    skipped = len(added) + len(changed) - len(alert_new) - len(alert_changed)
    if skipped:
        log.info("Not sent to Slack: %d new league fixture(s), stadium-only changes or matches less "
                 "than %d days away", skipped, ALERT_MIN_DAYS)
    messages = slack.build_messages(alert_new, alert_changed, excel_url(), first_run, counts["upcoming"], missing)
    if not messages:
        log.info("Nothing new to report to Slack.")
    elif args.no_slack or not webhook:
        log.info("Slack not sent (%s). Message preview:\n%s",
                 "--no-slack" if args.no_slack else "SLACK_WEBHOOK_URL not set",
                 json.dumps(messages, indent=1, ensure_ascii=False)[:4000])
    else:
        slack.post(webhook, messages)
        log.info("Posted %d Slack message(s)", len(messages))

    # Summary for the GitHub Actions run page
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(f"### Partner fixtures\n\n- New: {len(added)}\n- Changed: {len(changed)}\n"
                    f"- Upcoming in total: {counts['upcoming']}\n")
            if missing:
                f.write(f"- Not found on ESPN: {', '.join(missing)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
