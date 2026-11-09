"""Series winner model built from Liquipedia results only.

Writes results.json with aggregated results. Raw data and individual prices are never written.
Usage: python cs2_model.py
"""
import csv, json, os

import numpy as np

import cs2_core as c

FEATURES = ["elo", "form", "pelo", "rest", "pexp", "pfast", "prs"]
TEAM_ONLY = ["elo", "form", "rest"]
FIRST_MODEL = ["elo", "form"]
TRAIN_START = "2024-04"


def fit_model(rows, features=FEATURES):
    names = c.two(*features)
    X = np.array([[x[f] for f in names] for x in rows], float)
    y = np.array([x["y"] for x in rows], float)
    sd = np.maximum(np.sqrt((X ** 2).mean(0)), 1e-9)
    return dict(features=features, names=names, sd=sd, w=c.fit(X / sd, y))


def predict(model, rows):
    X = np.array([[x[f] for f in model["names"]] for x in rows], float)
    return 1 / (1 + np.exp(-((X / model["sd"]) @ model["w"])))


def walk_predict(S, features=FEATURES, folds=c.FOLDS):
    """Out-of-sample predictions: each fold is trained only on earlier months."""
    P = {}
    for lo, hi in zip(folds, folds[1:]):
        test = [i for i, x in enumerate(S) if lo <= x["month"] < hi]
        if test:
            model = fit_model([x for x in S if TRAIN_START <= x["month"] < lo], features)
            for i, p in zip(test, predict(model, [S[i] for i in test])):
                P[i] = float(p)
    return P


def main():
    D = c.load_data()
    S = c.build(D)[0]
    P = walk_predict(S)
    fin = [i for i, x in enumerate(S) if x["month"] >= c.SEL[1] and i in P]
    team = walk_predict(S, TEAM_ONLY)
    changed = [i for i in fin if S[i]["known"] and S[i]["stab"] < .8]
    stable = [i for i in fin if S[i]["known"] and S[i]["stab"] >= .8]
    out = dict(through=S[-1]["day"], series=len(S), formats={str(b): sum(x["bo"] == b for x in S) for b in (1, 3, 5)},
               all_from_may=dict(n=len(fin), model=c.score(P, S, fin), elo=c.score(walk_predict(S, ["elo"]), S, fin)),
               rosters=dict(changed=dict(n=len(changed), team_only=c.score(team, S, changed)[0], model=c.score(P, S, changed)[0], gain=c.gain(team, P, S, changed)),
                            stable=dict(n=len(stable), team_only=c.score(team, S, stable)[0], model=c.score(P, S, stable)[0], gain=c.gain(team, P, S, stable))))
    if os.path.exists("cs2_odds.csv"):
        matched, _ = c.match_odds(S, D.alias, list(csv.DictReader(open("cs2_odds.csv", encoding="utf8"))))
        matched = [x for x in matched if x["i"] in P]
        ids = [x["i"] for x in matched]
        market = {x["i"]: c.devig(x["pa"], x["pb"]) for x in matched}
        may = [i for i in ids if S[i]["month"] >= c.SEL[1]]
        elo, first = walk_predict(S, ["elo"]), walk_predict(S, FIRST_MODEL)
        for name, group in (("priced_all", ids), ("priced_from_may", may)):
            out[name] = dict(n=len(group), first_day=min(S[i]["day"] for i in group), last_day=max(S[i]["day"] for i in group), elo=c.score(elo, S, group), first_model=c.score(first, S, group),
                             model=c.score(P, S, group), pinnacle=c.score(market, S, group), market_lead=c.gain(P, market, S, group))
    with open("results.json", "w", encoding="utf8") as f:
        json.dump(out, f, indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
