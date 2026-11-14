"""Tests for the upcoming-match record on synthetic pages. Run: python -m pytest -q tests"""
import os, sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cs2_upcoming as u

NOW = datetime(2026, 11, 14, 18, 0, tzinfo=timezone.utc)
ALIAS = dict(furia="FURIA", spirit="Team Spirit", mouz="MOUZ")


def match(t1, t2, when, finished="", maps=3, score=""):
    slots = "".join(f"|map{i + 1}={{{{Map|map=|finished=|t1t={score}|t1ct=|t2t=|t2ct=}}}}\n" for i in range(maps))
    return f"{{{{Match\n|opponent1={{{{TeamOpponent|{t1}}}}}|opponent2={{{{TeamOpponent|{t2}}}}}\n|date={when} |finished={finished}\n{slots}}}}}\n"


def test_unplayed_match_is_found_with_utc_start_local_day_and_format():
    page = match("furia", "spirit", "November 15, 2026 - 03:00 {{Abbr/HKT}}", maps=5)
    (x,) = u.upcoming({"BLAST/Rivals": page}, NOW, ALIAS)
    assert (x["a"], x["b"], x["bo"], x["event"]) == ("FURIA", "Team Spirit", 5, "BLAST Rivals")
    assert x["start"] == datetime(2026, 11, 14, 19, 0, tzinfo=timezone.utc) and x["day"] == date(2026, 11, 15)


def test_finished_started_far_and_unknown_matches_are_left_out():
    pages = {"e": match("furia", "spirit", "November 15, 2026 - 16:00 {{Abbr/HKT}}", finished="true")
             + match("furia", "mouz", "November 15, 2026 - 16:00 {{Abbr/HKT}}", score="7")
             + match("furia", "mouz", "November 14, 2026 - 16:00 {{Abbr/HKT}}")
             + match("spirit", "mouz", "November 30, 2026 - 16:00 {{Abbr/HKT}}")
             + match("", "mouz", "November 15, 2026 - 16:00 {{Abbr/HKT}}")
             + match("unknown", "mouz", "November 15, 2026 - 16:00 {{Abbr/HKT}}")
             + match("spirit", "mouz", "November 15, 2026")
             + match("spirit", "mouz", "November 15, 2026 - 16:00 {{Abbr/XYZ}}")}
    assert u.upcoming(pages, NOW, ALIAS) == []


def test_log_row_is_frozen_once_the_match_has_started():
    x = dict(start=NOW + timedelta(hours=2), day=date(2026, 11, 14), a="FURIA", b="Team Spirit", bo=3, event="e")
    log = u.merge_log([], [(x, .6)], NOW, "2026-11-13")
    log = u.merge_log(log, [(x, .7)], NOW + timedelta(hours=1), "2026-11-14")
    assert [r["p_a"] for r in log] == ["0.7000"]
    later = NOW + timedelta(hours=3)
    log = u.merge_log(log, [(dict(x, start=later + timedelta(hours=1), a="MOUZ"), .5)], later, "2026-11-14")
    assert sorted(r["p_a"] for r in log) == ["0.5000", "0.7000"]
    assert next(r for r in log if r["team_a"] == "FURIA")["logged_at"] == "2026-11-14T19:00Z"


def test_result_is_read_for_the_logged_side():
    log = [dict(start="2026-11-14T20:00Z", day="2026-11-15", team_a="FURIA", team_b="Team Spirit", p_a="0.6500"),
           dict(start="2026-11-14T20:00Z", day="2026-11-15", team_a="MOUZ", team_b="FURIA", p_a="0.5000")]
    done = u.settle(log, [dict(day="2026-11-15", a="Team Spirit", b="FURIA", y=1)])
    assert [(r["team_a"], r["won_a"]) for r in done] == [("FURIA", 0)]
