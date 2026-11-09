"""Precompute series-winner prices for every pair of top teams on the expert dashboard.

Series format comes from map rows, which can miss maps, so derived markets such as total maps are not priced here.
Run cs2_expert_data.py first. Usage: python cs2_expert_prices.py   (writes dashboard/expert_prices.js)
"""
import json, re
from datetime import date
from itertools import combinations

import numpy as np

import cs2_core as c
import cs2_model as M

OUT = "dashboard/expert_prices.js"


def quote(model, state, a, b, ra, rb, bo, today):
    row = c.live_row(state, a, b, ra, rb, today, bo)
    p = float(M.predict(model, [row])[0])
    x = np.array([row[n] for n in model["names"]]) / model["sd"]
    suffix = "1" if bo == 1 else "3"
    parts = {n[:-1]: float(v * k) for n, v, k in zip(model["names"], x, model["w"]) if n.endswith(suffix)}
    assert abs(sum(parts.values()) - c.logit(p)) < 1e-6, (a, b, bo)
    return p, parts


def main():
    src = open("dashboard/expert_data.js", encoding="utf8").read()
    data = json.loads(re.fullmatch(r"window\.CS2_EXPERT = (.*);\s*", src, re.S).group(1))
    today = date.fromisoformat(data["asof"])
    names = [t["name"] for t in data["teams"]]
    S, _, state, _ = c.build(c.load_data())
    drift = [t["name"] for t in data["teams"] if abs(state["elo"][t["name"]] - t["elo"]) > .1]
    assert not drift, f"model and dashboard data disagree on {drift}"
    model = M.fit_model([x for x in S if M.TRAIN_START <= x["month"]])
    rosters = {n: state["last_roster"].get(n) for n in names}
    keys = M.FEATURES

    def row(p, parts):
        return [round(p, 4), [round(parts[k], 3) for k in keys]]

    pairs = {}
    for (i, a), (j, b) in combinations(enumerate(names), 2):
        ra, rb = rosters[a], rosters[b]
        out = []
        for bo in (1, 3):
            p, parts = quote(model, state, a, b, ra, rb, bo, today)
            back, _ = quote(model, state, b, a, rb, ra, bo, today)
            assert abs(p + back - 1) < 1e-9, (a, b, bo)
            out += row(p, parts)
        pairs[f"{i}-{j}"] = out
    result = dict(asof=data["asof"], version="liquipedia", teams=names, keys=keys, pairs=pairs)
    with open(OUT, "w", encoding="utf8") as f:
        f.write("window.CS2_PRICES = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("as of", data["asof"], "pairs", len(pairs), "keys", keys)


if __name__ == "__main__":
    main()
