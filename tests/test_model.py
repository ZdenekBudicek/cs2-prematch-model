"""Leakage and integrity tests on small synthetic data. Run: python -m pytest -q tests"""
import copy, os, sys
from datetime import date

import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cs2_core as c
import cs2_model as M

ROSTERS = {t: dict(players=[f"{t}{i}" for i in range(5)], loans=0) for t in "abcdef"}
NORMED = {c.norm(k): v for k, v in ROSTERS.items()}
EVENTS = {"e1": dict(tier=2, lan=0.0, qual=0, rosters=NORMED), "e2": dict(tier=3, lan=1.0, qual=0, rosters=NORMED)}
FEATS = ["elo", "form", "pelo", "rest", "pexp", "pfast", "prs"]


def maps(day, t1, t2, wins1, page="e1"):
    return [dict(date=day, team1=t1, team2=t2, map_no=str(i + 1), map="Mirage", score1="13" if w else "5",
                 score2="5" if w else "13", page=page) for i, w in enumerate(wins1)]


def sample():
    rows = []
    for k, (t1, t2) in enumerate([("a", "b"), ("c", "d"), ("a", "c"), ("b", "d"), ("e", "f"), ("a", "e")]):
        rows += maps(f"2025-01-{k + 1:02d}", t1, t2, [1, 1])
    rows += maps("2025-01-10", "a", "d", [1, 0, 1], "e2") + maps("2025-01-10", "b", "c", [1, 1], "e2")
    rows += maps("2025-01-11", "a", "b", [0, 0], "e2")
    return rows


def by_pair(S):
    return {(x["day"], frozenset((x["a"], x["b"]))): x for x in S}


def run(rows, events=EVENTS, **kw):
    return by_pair(c.build(c.make_data(copy.deepcopy(rows), events), **kw)[0])


def same(x, y):
    return all(x[f + s] == pytest.approx(y[f + s]) for f in FEATS for s in "13" if x["bo"] == y["bo"])


def test_future_results_do_not_change_earlier_features():
    base = sample()
    changed = [dict(r, score1=r["score2"], score2=r["score1"]) if r["date"] == "2025-01-11" else r for r in base]
    A, B = run(base), run(changed)
    assert all(same(x, B[k]) for k, x in A.items() if k[0] < "2025-01-11")


def test_same_day_result_does_not_reach_same_day_series():
    base = sample()
    changed = [dict(r, score1=r["score2"], score2=r["score1"]) if r["date"] == "2025-01-10" and r["team1"] == "b" else r for r in base]
    k = ("2025-01-10", frozenset("ad"))
    assert same(run(base)[k], run(changed)[k])


def test_lagged_roster_ignores_current_event_roster():
    base = sample()
    ev = copy.deepcopy(EVENTS)
    ev["e2"]["rosters"][c.norm("a")] = dict(players=["x1", "x2", "x3", "x4", "x5"], loans=0)
    k = ("2025-01-10", frozenset("ad"))
    A, B = run(base, lag=True), run(base, ev, lag=True)
    assert same(A[k], B[k])
    assert run(base, ev)[k]["pelo3"] != pytest.approx(A[k]["pelo3"])


def test_walk_forward_ignores_later_labels():
    rng = np.random.default_rng(1)
    months = ["2024-05"] * 80 + ["2025-02"] * 80 + ["2025-06"] * 80
    rows = [dict(month=m, x=float(rng.normal()), y=int(rng.random() < .5)) for m in months]
    folds = ["2025-01", "2025-05", "2025-09"]
    P = c.walk(rows, ["x"], folds)
    flipped = [dict(r, y=1 - r["y"]) if r["month"] == "2025-06" else r for r in rows]
    Q = c.walk(flipped, ["x"], folds)
    assert all(P[i] == pytest.approx(Q[i]) for i, r in enumerate(rows) if r["month"] != "2025-06" and i in P)
    assert all(i >= 80 for i in P)


def test_swapping_teams_flips_probability():
    rng = np.random.default_rng(2)
    X = rng.normal(size=(400, 3)); y = (X @ [1, -1, .5] + rng.normal(size=400) > 0).astype(float)
    w = c.fit(X, y)
    x = np.array([.7, -.2, 1.1])
    assert c.sig(float(x @ w)) + c.sig(float(-x @ w)) == pytest.approx(1)


def test_devig_sums_to_one():
    assert c.devig(1.5, 2.6) + c.devig(2.6, 1.5) == pytest.approx(1)


def test_qualifier_does_not_inherit_main_event_rosters():
    ev = {"q": dict(tier=1, lan=0.0, qual=1, own={}, rosters=NORMED)}
    rows = maps("2025-01-01", "a", "b", [1, 1], "q") + maps("2025-01-05", "a", "b", [1, 1], "q")
    assert c.build(c.make_data(rows, ev))[3]["both rosters"] == 0


def test_one_known_roster_gives_no_signal():
    ev = {"m": dict(tier=2, lan=0.0, qual=0, rosters={c.norm("a"): ROSTERS["a"]})}
    rows = maps("2025-01-01", "a", "b", [1, 1], "m") + maps("2025-01-05", "a", "b", [1, 1], "m")
    S = c.build(c.make_data(rows, ev))[0]
    assert all(x["pexp3"] == 0 and x["pelo3"] == pytest.approx(x["elo3"]) for x in S)


def test_live_row_matches_training_row():
    rows = sample() + maps("2025-01-20", "a", "b", [1, 1], "e2")
    S = c.build(c.make_data(copy.deepcopy(rows), EVENTS))[0]
    st = c.build(c.make_data(copy.deepcopy([r for r in rows if r["date"] < "2025-01-20"]), EVENTS))[2]
    x = next(x for x in S if x["day"] == "2025-01-20")
    live = c.live_row(st, x["a"], x["b"], ROSTERS[x["a"]]["players"], ROSTERS[x["b"]]["players"], date(2025, 1, 20), x["bo"])
    for k in FEATS:
        assert live[k + "3"] == pytest.approx(x[k + "3"]), k


def test_trace_leaves_results_unchanged():
    seen = []
    plain = c.build(c.make_data(copy.deepcopy(sample()), EVENTS))[0]
    traced = c.build(c.make_data(copy.deepcopy(sample()), EVENTS), trace=seen.append)[0]
    assert seen and plain == traced


def train_rows(n=600):
    rng = np.random.default_rng(3)
    base = np.datetime64("2024-05-01")
    rows = []
    for i in range(n):
        day = str(base + np.timedelta64(i, "D"))[:10]
        v = rng.normal(size=len(FEATS))
        r = dict(day=day, month=day[:7], bo=3, y=int(rng.random() < c.sig(float(v[0] + v[2]))))
        for f, a in zip(FEATS, v):
            r[f + "1"], r[f + "3"] = 0.0, float(a)
        rows.append(r)
    return rows


def test_model_flips_when_teams_swap():
    rows = train_rows()
    model = M.fit_model(rows)
    row = rows[0]
    swapped = {k: -v if k[:-1] in FEATS else v for k, v in row.items()}
    assert float(M.predict(model, [row])[0]) + float(M.predict(model, [swapped])[0]) == pytest.approx(1)


def test_model_walk_ignores_later_labels():
    rows = train_rows()
    folds = ["2025-01", "2025-05", "2025-09"]
    P = M.walk_predict(rows, folds=folds)
    flipped = [dict(r, y=1 - r["y"]) if r["month"] >= "2025-05" else r for r in rows]
    Q = M.walk_predict(flipped, folds=folds)
    assert P and all(P[i] == pytest.approx(Q[i]) for i in P if rows[i]["month"] < "2025-05")
