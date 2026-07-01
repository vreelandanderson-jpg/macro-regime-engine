"""Print the automatic upcoming event calendar.

This does not need MT5 or Excel. It is useful for checking that the auto calendar
is populated outside the dashboard.
"""

from __future__ import annotations

import argparse

from auto_events import build_auto_event_calendar


def main() -> None:
    parser = argparse.ArgumentParser(description="Show automatic macro/AI event calendar.")
    parser.add_argument("--months", type=int, default=6, help="Months ahead to generate")
    parser.add_argument("--offline", action="store_true", help="Skip live official/API sources")
    args = parser.parse_args()

    calendar = build_auto_event_calendar(months_ahead=args.months, include_live_sources=not args.offline)
    if calendar.empty:
        print("No events generated.")
        return
    print(calendar.to_string(index=False))


if __name__ == "__main__":
    main()
