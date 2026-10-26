"""Sanity-check required fields in the historical event compilation."""

from resq.events import load_events


def main() -> None:
    events = load_events()
    assert len(events) == 3, "The big-three validation set must contain exactly three events."
    dates = {event.event_date.isoformat() for event in events}
    assert {"2019-08-10", "2024-07-31", "2026-08-03"}.issubset(dates), "Required validation dates are missing."
    assert all(event.water_level_m > 0 and event.source_urls for event in events)
    print(f"Validated {len(events)} event records; {sum(len(e.source_urls) for e in events)} source URLs present.")


if __name__ == "__main__":
    main()
