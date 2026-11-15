"""Glicko-2 against round-margin Elo in the public Liquipedia-only model, under the same rules as its other choices.

Glicko-2 adds a rating deviation (RD) per team: it grows while a team is inactive and shrinks as it plays, so a team
with little data gets a wider, more cautious prediction. Rules fixed before results were seen:
- Settings (tau, initial RD, days per rating period, binary or round-share score) are chosen on map log loss of
  Apr to Dec 2024 only, as the Elo K was.
- Each day is one rating period: ratings are frozen within a day, like every rating in cs2_core.build.
- Series models are scored with the same expanding walk-forward. A Glicko input enters the model only if it gains at least
  0.0005 log loss on the selection window (May 2025 to Apr 2026). May 2026 onward and Pinnacle are read afterwards.
Usage: .venv/Scripts/python cs2_glicko.py   (writes cs2_glicko_results.json)
"""
import csv, json, math, os
from collections import defaultdict
from itertools import product

import numpy as np

import cs2_core as c

Q = 173.7178
D = c.load_data()
MAPS = []
S, _, _, _ = c.build(D, trace=lambda t: MAPS.append((t["day"], t["a"], t["b"], t["won"], t["share"])))
DAYS = sorted({m[0] for m in MAPS})
FEAT = ["elo", "form", "pelo", "rest", "pexp", "pfast", "prs"]   # the public model's inputs, cs2_model.FEATURES


def gfun(phi):
    return 1 / math.sqrt(1 + 3 * phi * phi / math.pi ** 2)


def new_sigma(sigma, phi, v, delta, tau):
    a = math.log(sigma * sigma)
    f = lambda x: (math.exp(x) * (delta ** 2 - phi ** 2 - v - math.exp(x)) / (2 * (phi ** 2 + v + math.exp(x)) ** 2)
                   - (x - a) / tau ** 2)
    A = a
    if delta ** 2 > phi ** 2 + v:
        B = math.log(delta ** 2 - phi ** 2 - v)
    else:
        k = 1
        while f(a - k * tau) < 0:
            k += 1
        B = a - k * tau
    fa, fb = f(A), f(B)
    for _ in range(60):
        if abs(B - A) < 1e-6:
            break
        C = A + (A - B) * fa / (fb - fa)
        fc = f(C)
        if fc * fb <= 0:
            A, fa = B, fb
        else:
            fa /= 2
        B, fb = C, fc
    return math.exp(A / 2)


def run(tau=.5, rd0=350, period=7, score="win", sigma0=.06):
    """Replay all maps day by day. Returns pre-day state lookups and map-level predictions."""
    mu, phi, sig, last = defaultdict(float), defaultdict(lambda: rd0 / Q), defaultdict(lambda: sigma0), {}
    phimax = rd0 / Q
    by_day = defaultdict(list)
    for m in MAPS:
        by_day[m[0]].append(m)
    snap, pred = {}, []

    def cur_phi(t, day):
        if t not in last:
            return phimax
        gap = (day - last[t]).days
        return min(math.sqrt(phi[t] ** 2 + sig[t] ** 2 * gap / period), phimax)

    for day in DAYS:
        ms = by_day[day]
        teams = {x for m in ms for x in (m[1], m[2])}
        pre = {t: (mu[t], cur_phi(t, day)) for t in teams}
        snap[day] = pre
        games = defaultdict(list)
        for _, a, b, won, share in ms:
            s = won if score == "win" else share
            games[a].append((b, s)); games[b].append((a, 1 - s))
            ma, pa = pre[a]; mb, pb = pre[b]
            pred.append((day, won, 1 / (1 + math.exp(-gfun(math.hypot(pa, pb)) * (ma - mb)))))
        for t, gl in games.items():
            m0, p0 = pre[t]
            vinv, dsum = 0.0, 0.0
            for o, s in gl:
                mo, po = pre[o]
                g = gfun(po); e = 1 / (1 + math.exp(-g * (m0 - mo)))
                vinv += g * g * e * (1 - e); dsum += g * (s - e)
            v = 1 / vinv; delta = v * dsum
            sg = new_sigma(sig[t], p0, v, delta, tau)
            ps = math.sqrt(p0 ** 2 + sg ** 2)
            p1 = 1 / math.sqrt(1 / ps ** 2 + 1 / v)
            mu[t] = m0 + p1 ** 2 * dsum; phi[t] = p1; sig[t] = sg; last[t] = day
    return snap, pred, (mu, phi, last)


def map_ll(pred, lo, hi):
    v = [c.ll(p, y) for d, y, p in pred if lo <= d.isoformat()[:7] <= hi]
    return sum(v) / len(v), len(v)


def add_features(snap, rows, rd0):
    """Glicko inputs for each series from that day's pre-period state; unseen teams sit at the start values."""
    for r in rows:
        day = c.date.fromisoformat(r["day"])
        pre = snap.get(day, {})
        ma, pa = pre.get(r["a"], (0.0, rd0 / Q)); mb, pb = pre.get(r["b"], (0.0, rd0 / Q))
        f = dict(gl=(ma - mb) * Q,                                   # rating difference, Elo-like scale
                 glx=gfun(math.hypot(pa, pb)) * (ma - mb),           # Glicko map logit, shrunk by both RDs
                 glrd=(ma - mb) * Q * (math.hypot(pa, pb) - .5))     # lets the model learn its own shrinkage
        for k, v in f.items():
            r[k + "1"] = v if r["bo"] == 1 else 0.0
            r[k + "3"] = v if r["bo"] > 1 else 0.0


# 1) choose settings on Apr to Dec 2024 map log loss
grid = list(product((.3, .5, 1.0), (200, 350), (1, 7, 30), ("win", "share")))
tune = {}
for tau, rd0, per, sc in grid:
    tune[(tau, rd0, per, sc)] = map_ll(run(tau, rd0, per, sc)[1], "2024-04", "2024-12")[0]
best = min(tune, key=tune.get)
first_best = best
if best[1] == 350 or best[2] == 1:                 # on the grid edge: widen once, as for the Elo K
    for tau, rd0, per, sc in product((.3, .5, 1.0), (350, 500, 700), (.25, .5, 1), ("win", "share")):
        if (tau, rd0, per, sc) not in tune:
            tune[(tau, rd0, per, sc)] = map_ll(run(tau, rd0, per, sc)[1], "2024-04", "2024-12")[0]
    best = min(tune, key=tune.get)
print("tuning, map log loss Apr-Dec 2024, best 5:")
for k in sorted(tune, key=tune.get)[:5]:
    print("  tau %.1f rd0 %d period %2d %-5s %.4f" % (*k, tune[k]))
edge = [n for n, v, ends in zip(("tau", "rd0", "period"), best, ((.3, 1.0), (200, 700), (.25, 30))) if v in ends]
print("BEST", best, "on grid edge:", edge or "none")
snap, pred, (MU, PHI, LAST) = run(*best)
add_features(snap, S, best[1])

sel = [i for i, x in enumerate(S) if c.SEL[0] <= x["month"] < c.SEL[1]]
fin = [i for i, x in enumerate(S) if x["month"] >= c.SEL[1]]
res = dict(settings=dict(zip(("tau", "rd0", "period", "score"), best)), first_grid_best=list(first_best), tune_ll=tune[best],
           tune_top=[[list(k), v] for k, v in sorted(tune.items(), key=lambda t: t[1])[:5]])

# 2) alone: Elo against Glicko as the only rating input
P = {k: c.walk(S, c.two(*f)) for k, f in (("elo", ["elo"]), ("elo+unc", ["elo", "unc"]), ("glicko diff", ["gl"]),
                                          ("glicko logit", ["glx"]), ("glicko diff + rd", ["gl", "glrd"]))}
res["alone"] = {}
for k, q in P.items():
    res["alone"][k] = dict(sel=c.score(q, S, sel), fin=c.score(q, S, fin),
                           gain_sel=c.gain(P["elo"], q, S, sel, 1000) if k != "elo" else None,
                           gain_fin=c.gain(P["elo"], q, S, fin, 1000) if k != "elo" else None)
    print("alone %-18s sel %.4f fin %.4f" % (k, res["alone"][k]["sel"][0], res["alone"][k]["fin"][0]),
          "" if k == "elo" else "gain vs elo sel %+.4f [%+.4f, %+.4f]" % res["alone"][k]["gain_sel"])

# 3) inside the model: add a Glicko input, or swap it for Elo, chosen on the selection window only
base = c.walk(S, c.two(*FEAT))
cands = {"model + glicko diff + rd": FEAT + ["gl", "glrd"], "model + glicko logit": FEAT + ["glx"],
         "model, glicko diff instead of elo": [f if f != "elo" else "gl" for f in FEAT],
         "model, glicko logit instead of elo": [f if f != "elo" else "glx" for f in FEAT]}
res["model"] = dict(base_sel=c.score(base, S, sel), base_fin=c.score(base, S, fin), cands={})
for k, f in cands.items():
    q = c.walk(S, c.two(*f))
    res["model"]["cands"][k] = dict(sel=c.score(q, S, sel), fin=c.score(q, S, fin), gain_sel=c.gain(base, q, S, sel, 1000),
                                 gain_fin=c.gain(base, q, S, fin, 1000))
    P[k] = q
    print("%-34s gain sel %+.4f [%+.4f, %+.4f]  fin %+.4f [%+.4f, %+.4f]" % (k, *res["model"]["cands"][k]["gain_sel"], *res["model"]["cands"][k]["gain_fin"]))
pick = max(res["model"]["cands"], key=lambda k: res["model"]["cands"][k]["gain_sel"][0])
res["model"]["decision"] = pick if res["model"]["cands"][pick]["gain_sel"][0] >= .0005 else "keep model"
print("DECISION", res["model"]["decision"])

# 4) where Glicko should help: teams with little data (fewer than 30 earlier maps for either team)
cnt = defaultdict(int); low = set()
by_day = defaultdict(list)
for m in MAPS:
    by_day[m[0]].append(m)
rows_by_day = defaultdict(list)
for i, r in enumerate(S):
    rows_by_day[r["day"]].append(i)
for d in DAYS:
    for i in rows_by_day.get(d.isoformat(), []):
        if min(cnt[S[i]["a"]], cnt[S[i]["b"]]) < 30:
            low.add(i)
    for _, a, b, _, _ in by_day[d]:
        cnt[a] += 1; cnt[b] += 1
best_add = P[pick]
res["segments"] = {}
for name, ids in (("fewer than 30 maps", [i for i in fin if i in low]), ("both 30+ maps", [i for i in fin if i not in low])):
    res["segments"][name] = dict(n=len(ids), elo_alone=c.score(P["elo"], S, ids)[0], glicko_alone=c.score(P["glicko diff + rd"], S, ids)[0],
                                 model=c.score(base, S, ids)[0], model_glicko=c.score(best_add, S, ids)[0],
                                 gain_alone=c.gain(P["elo"], P["glicko diff + rd"], S, ids, 1000), gain_model=c.gain(base, best_add, S, ids, 1000))
    print("segment %-20s n %4d alone gain %+.4f [%+.4f, %+.4f]  model gain %+.4f [%+.4f, %+.4f]" % (
        name, len(ids), *res["segments"][name]["gain_alone"], *res["segments"][name]["gain_model"]))

# 5) against Pinnacle, read last
if os.path.exists("cs2_odds.csv"):          # private price file; skipped without it, as in cs2_model.py
    odds = list(csv.DictReader(open("cs2_odds.csv", encoding="utf8")))
    matched, _ = c.match_odds(S, D.alias, odds)
    idx = [m["i"] for m in matched if m["i"] in base]
    MK = {m["i"]: c.devig(m["pa"], m["pb"]) for m in matched}
    res["market"] = dict(n=len(idx), model=c.score(base, S, idx), model_glicko=c.score(best_add, S, idx), pinnacle=c.score(MK, S, idx),
                         elo_alone=c.score(P["elo"], S, idx), glicko_alone=c.score(P["glicko diff + rd"], S, idx))
    print("matched %d: model %.4f, %s %.4f, Pinnacle %.4f; alone elo %.4f glicko %.4f" % (
        len(idx), res["market"]["model"][0], pick, res["market"]["model_glicko"][0], res["market"]["pinnacle"][0],
        res["market"]["elo_alone"][0], res["market"]["glicko_alone"][0]))
    res["market"]["gain_model_glicko"] = c.gain(base, best_add, S, idx, 2000)
    res["market"]["gap_model"] = c.gain(base, MK, S, idx, 2000)
    res["market"]["gap_model_glicko"] = c.gain(best_add, MK, S, idx, 2000)
    print("priced: glicko gain over the model %+.4f [%+.4f, %+.4f]; market lead model %+.4f, with glicko %+.4f" % (
        *res["market"]["gain_model_glicko"], res["market"]["gap_model"][0], res["market"]["gap_model_glicko"][0]))
    tiers = defaultdict(list)
    for i in fin:
        tiers[S[i]["tier"]].append(i)
    res["tiers"] = {str(t): dict(n=len(ids), gain=c.gain(base, best_add, S, ids, 1000)) for t, ids in sorted(tiers.items())}
    for t, v in res["tiers"].items():
        print("tier %s n %4d glicko gain over the model %+.4f [%+.4f, %+.4f]" % (t, v["n"], *v["gain"]))
json.dump(res, open("cs2_glicko_results.json", "w", encoding="utf8"), indent=1, default=float)
