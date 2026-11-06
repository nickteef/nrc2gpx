"""Command-line interface for NRC2GPX."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Sequence

import requests

from . import __version__
from .api import AuthError, NikeAPIError, NikeClient, RunSummary
from .gpx import build_gpx

EPILOG = """examples:
  nrc2gpx list -t TOKEN
  nrc2gpx export -t TOKEN                     # every run with GPS
  nrc2gpx export -t TOKEN --latest            # only the most recent run
  nrc2gpx export -t TOKEN --latest 5
  nrc2gpx export -t TOKEN --since 2026-01-01 --until 2026-06-30
  nrc2gpx export -t TOKEN --pick              # choose interactively
  nrc2gpx export -t TOKEN --id <activity-id>
"""


# ---------------------------------------------------------------- helpers

def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date '{value}', expected YYYY-MM-DD")


def parse_selection(text: str, count: int) -> list[int]:
    """Parse '1,3,5-8' or 'all' into sorted zero-based indices (input is 1-based)."""
    text = text.strip().lower()
    if text in ("all", "a", "*"):
        return list(range(count))
    picked: set[int] = set()
    for part in text.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            lo_s, hi_s = part.split("-", 1)
            lo, hi = int(lo_s), int(hi_s)
            if lo > hi:
                lo, hi = hi, lo
        else:
            lo = hi = int(part)
        if lo < 1 or hi > count:
            raise ValueError(f"'{part}' is out of range (1-{count})")
        picked.update(range(lo - 1, hi))
    return sorted(picked)


def fmt_duration(ms: Optional[int]) -> str:
    if not ms:
        return "-"
    s = int(round(ms / 1000))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_pace(sec_per_km: Optional[float]) -> str:
    if not sec_per_km:
        return "-"
    m, s = divmod(int(round(sec_per_km)), 60)
    return f"{m}:{s:02d}/km"


def print_table(runs: Sequence[RunSummary]) -> None:
    header = f"{'#':>4}  {'Date':<16}  {'Distance':>9}  {'Duration':>8}  {'Pace':>9}  {'GPS':<3}  Name"
    print(header)
    print("-" * len(header))
    for i, r in enumerate(runs, 1):
        dist = f"{r.distance_km:.2f} km" if r.distance_km else "-"
        gps = {True: "yes", False: "no", None: "?"}[r.has_gps]
        print(
            f"{i:>4}  {r.start:%Y-%m-%d %H:%M}  {dist:>9}  {fmt_duration(r.duration_ms):>8}  "
            f"{fmt_pace(r.pace_s_per_km):>9}  {gps:<3}  {r.name or ''}"
        )


def filter_by_date(runs: list[RunSummary], since: Optional[date], until: Optional[date]) -> list[RunSummary]:
    if since:
        start = datetime.combine(since, datetime.min.time())
        runs = [r for r in runs if r.start >= start]
    if until:
        end = datetime.combine(until + timedelta(days=1), datetime.min.time())
        runs = [r for r in runs if r.start < end]
    return runs


def get_token(args: argparse.Namespace) -> str:
    if args.token:
        return args.token
    sys.exit("error: a Nike bearer token is required (-t/--token). See README for how to get one.")


def fetch_runs(client: NikeClient, args: argparse.Namespace) -> list[RunSummary]:
    print("Fetching activity list from Nike ...", file=sys.stderr)
    runs = filter_by_date(client.list_runs(), args.since, args.until)
    if not runs:
        sys.exit("No runs found for the given filters.")
    return runs


# --------------------------------------------------------------- commands

def cmd_list(client: NikeClient, args: argparse.Namespace) -> int:
    runs = fetch_runs(client, args)
    print_table(runs)
    print(f"\n{len(runs)} run(s).")
    return 0


def choose_interactively(runs: list[RunSummary]) -> list[RunSummary]:
    print_table(runs)
    print()
    while True:
        try:
            answer = input("Runs to export (e.g. 1,3,5-8 or 'all'; Enter to cancel): ")
        except EOFError:
            return []
        if not answer.strip():
            return []
        try:
            return [runs[i] for i in parse_selection(answer, len(runs))]
        except ValueError as e:
            print(f"  Invalid selection: {e}")


def select_runs(runs: list[RunSummary], args: argparse.Namespace) -> list[RunSummary]:
    if args.pick:
        return choose_interactively(runs)
    if args.latest:
        return [r for r in runs if r.has_gps is not False][: args.latest]
    return runs


def output_name(activity: dict) -> str:
    start = datetime.fromtimestamp(activity["start_epoch_ms"] / 1000)
    return f"{start:%Y-%m-%d_%H-%M}_nrc"


def cmd_export(client: NikeClient, args: argparse.Namespace) -> int:
    if args.ids:
        # Fetch the requested activities directly, no need for the full list.
        selected = [RunSummary(id=i, start_ms=0, duration_ms=None, distance_km=None,
                               name=None, has_gps=None) for i in dict.fromkeys(args.ids)]
    else:
        selected = select_runs(fetch_runs(client, args), args)
    if not selected:
        print("Nothing selected.")
        return 0

    candidates = [r for r in selected if r.has_gps is not False]
    skipped_no_gps = len(selected) - len(candidates)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    written = existing = empty = 0
    total = len(candidates)
    for i, run in enumerate(candidates, 1):
        prefix = f"[{i}/{total}]"
        if run.start_ms and not args.overwrite:
            guess = out / f"{run.start:%Y-%m-%d_%H-%M}_nrc.gpx"
            if guess.exists():
                print(f"{prefix} {guess.name} already exists, skipping")
                existing += 1
                continue

        activity = client.get_activity(run.id)
        base = output_name(activity)
        if args.raw:
            (out / f"{base}.json").write_text(json.dumps(activity, indent=2), encoding="utf-8")

        gpx = build_gpx(activity)
        if gpx is None:
            print(f"{prefix} {base}: no GPS data (treadmill/indoor run?), skipping")
            empty += 1
            continue

        path = out / f"{base}.gpx"
        if path.exists() and not args.overwrite:
            print(f"{prefix} {path.name} already exists, skipping")
            existing += 1
            continue
        path.write_text(gpx, encoding="utf-8")
        print(f"{prefix} wrote {path}")
        written += 1

    print(f"\nDone. {written} GPX file(s) written to '{out}'.")
    extras = []
    if existing:
        extras.append(f"{existing} already existed (use --overwrite)")
    if empty + skipped_no_gps:
        extras.append(f"{empty + skipped_no_gps} without GPS")
    if extras:
        print("Skipped: " + ", ".join(extras) + ".")
    return 0


# ------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-t", "--token", help="Nike bearer token (with or without 'Bearer ')")
    common.add_argument("--since", type=parse_date, metavar="YYYY-MM-DD",
                        help="only runs on or after this date")
    common.add_argument("--until", type=parse_date, metavar="YYYY-MM-DD",
                        help="only runs on or before this date")

    p = argparse.ArgumentParser(
        prog="nrc2gpx",
        description="Export your Nike Run Club runs as GPX files.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    sub.add_parser("list", parents=[common], help="list your runs")

    e = sub.add_parser("export", parents=[common], help="export runs as GPX (default: all)")
    which = e.add_mutually_exclusive_group()
    which.add_argument("--latest", nargs="?", type=int, const=1, metavar="N",
                       help="export only the N most recent runs (default N=1)")
    which.add_argument("--pick", action="store_true",
                       help="show a numbered list and choose which runs to export")
    which.add_argument("--id", dest="ids", action="append", metavar="ID",
                       help="export a specific activity ID (repeatable)")
    e.add_argument("-o", "--output", default="nrc_gpx", help="output folder (default: nrc_gpx)")
    e.add_argument("--overwrite", action="store_true", help="overwrite existing GPX files")
    e.add_argument("--raw", action="store_true", help="also save the raw JSON of each activity")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "latest", None) is not None and args.latest < 1:
        sys.exit("error: --latest must be at least 1")

    client = NikeClient(get_token(args))
    try:
        if args.command == "list":
            return cmd_list(client, args)
        return cmd_export(client, args)
    except AuthError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except NikeAPIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"error: network problem: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
