#!/usr/bin/env python3
"""The status date is the newest checker run, and every stored run stays in history."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from derive import (apply_latest_run, check_history, enrich, history_from, latest_run, load,
                    newest_entries, stats)


def test_latest_run_counts_only_that_date():
    history = {
        ("2026-10-21", "https://a.example"): (False, "err"),
        ("2026-10-21", "https://b.example"): (True, None),
        ("2026-10-22", "https://a.example"): (True, None),
        ("2026-10-22", "https://c.example"): (True, None),
    }
    run = latest_run(history)
    assert run == {"date": "2026-10-22", "sources": 2, "errors": 0, "ok": 2}, run


def test_newest_entry_prefers_later_check_over_later_commit():
    restored_old = {"https://a.example": {"last_checked": "2026-10-21", "last_attempt": "2026-10-21",
                                           "last_error": "boom"}}
    earlier_commit = {"https://a.example": {"last_checked": "2026-10-22", "last_attempt": "2026-10-22",
                                             "last_error": None}}
    best = newest_entries([restored_old, earlier_commit])
    assert best["https://a.example"]["last_checked"] == "2026-10-22"


def test_history_keeps_every_date():
    versions = [
        {"https://a.example": {"last_checked": "2026-10-21", "last_error": None}},
        {"https://a.example": {"last_checked": "2026-10-22", "last_error": None},
         "https://b.example": {"last_checked": "2026-10-22", "last_error": None}},
    ]
    dates = {d for d, _u in history_from(versions)}
    assert dates == {"2026-10-21", "2026-10-22"}


def test_repo_runs():
    """Both checker runs stored in git. The newest one is the 2026-10-22 nightly report."""
    data, _, snaps = load()
    history = check_history(snaps)
    by_date = {}
    for (d, _u), (ok, _err) in history.items():
        slot = by_date.setdefault(d, {"sources": 0, "errors": 0})
        slot["sources"] += 1
        slot["errors"] += 0 if ok else 1
    assert by_date["2026-10-21"] == {"sources": 108, "errors": 3}, by_date.get("2026-10-21")
    assert by_date["2026-10-22"] == {"sources": 116, "errors": 0}, by_date.get("2026-10-22")
    run = latest_run(history)
    assert run["date"] == max(by_date)
    assert run["sources"] == by_date[run["date"]]["sources"]
    assert run["errors"] == by_date[run["date"]]["errors"]
    st = apply_latest_run(stats(enrich(data["vendors"]), snaps), history)
    assert st["full_check"] == run["date"] == st["monitor_last"]
    assert st["monitored_pages"] == run["sources"]
    assert st["monitor_errors"] == run["errors"]
    assert run["date"] == "2026-10-22"
    assert run["sources"] == 116 and run["errors"] == 0


if __name__ == "__main__":
    test_latest_run_counts_only_that_date()
    test_newest_entry_prefers_later_check_over_later_commit()
    test_history_keeps_every_date()
    test_repo_runs()
    print("ok")
