"""Shared, testable core for the CS2 models: data loading, ratings, features, fitting, scoring.

Features for a series use only what was known before that day. Results of a day reach the ratings
after the day ends.
"""
import csv, json, math, random, re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date
from itertools import combinations

import numpy as np

K = 32                                              # chosen before 2025, see cs2_map_model_v3.py
STOP = {"team", "esports", "esport", "gaming", "club", "gg", "e", "sports", "clan"}
FOLDS = ["2025-01", "2025-05", "2025-09", "2026-01", "2026-05", "2026-08", "2026-12"]
MAP_FOLDS = ["2025-01", "2025-05", "2025-09", "2026-01", "2026-05", "2026-12"]
SEL = ("2025-05", "2026-05")                        # selection window for series models
expected = lambda d: 1 / (1 + 10 ** (-d / 400))
sig = lambda z: 1 / (1 + math.exp(-z))
logit = lambda p: math.log(p / (1 - p))


def norm(s):
    s = re.sub(r"\(.*?\)", " ", s.lower())
    parts = [t for t in re.findall(r"[a-z0-9]+", s) if t not in STOP]
    return "".join(parts) or re.sub(r"\W", "", s)


def ll(p, t):
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -(t * math.log(p) + (1 - t) * math.log(1 - p))


@dataclass
class Data:
    series: dict
    order: list
    events: dict
    alias: dict


def make_data(map_rows, events, alias=None):
    """map_rows: dicts with date, team1, team2, map_no, map, score1, score2, page."""
    alias = alias or {}
    uniq = {}
    for r in map_rows:
        r = dict(r, raw1=r["team1"], raw2=r["team2"])
        r["team1"], r["team2"] = alias.get(r["team1"], r["team1"]), alias.get(r["team2"], r["team2"])
        uniq.setdefault((r["date"], frozenset((r["team1"], r["team2"])), r["map_no"]), r)
    rows = [r for r in uniq.values() if r["team1"] != r["team2"] and r["map"] not in ("Thera", "Cobblestone")]
    rows.sort(key=lambda r: (r["date"], r["team1"], int(r["map_no"])))
    series = defaultdict(list)
    for r in rows:
        series[(r["date"], frozenset((r["team1"], r["team2"])))].append(r)
    order = sorted(series, key=lambda k: (k[0], sorted(k[1])))
    return Data(series, order, events, alias)


def load_data(maps="cs2_maps.csv", aliases="team_aliases.json", events="cs2_events.json"):
    return make_data(list(csv.DictReader(open(maps, encoding="utf8"))), json.load(open(events, encoding="utf8")),
                     json.load(open(aliases, encoding="utf8")))


def build(data, KP=64, lag=False, KM=1, KR=300, trace=None):
    """Return series rows, map rows, final state and counters. If given, trace receives each map after its rating updates."""
    rng = random.Random(5)
    elo = defaultdict(lambda: 1500.0); fast = defaultdict(lambda: 1500.0); off = defaultdict(float)
    pl, pfast, ptier = {}, {}, {}
    last10 = defaultdict(lambda: deque(maxlen=10)); lvl = defaultdict(lambda: deque(maxlen=30))
    pm = defaultdict(int); pair = defaultdict(int); pms = defaultdict(int); pact = {}
    rr = defaultdict(float); prr = {}
    dec = defaultdict(lambda: deque(maxlen=20))     # did the team's recent BO3 series reach a third map?
    prev, n, seen, hist = {}, defaultdict(int), {}, defaultdict(list)
    S, M, stats = [], [], Counter()
    pending, cur_rosters, curday = [], {}, None

    def flush():
        for a, b, ra, rb, res, tier, page, today, bo3_maps in pending:
            pa = ra["players"] if ra else None
            pb = rb["players"] if rb else None
            tw = {3: 1.5, 2: 1.2}.get(tier, 1.0)
            for m, s, rd in res:
                e = e0 = expected(elo[a] - elo[b])
                dw = (elo[a] - elo[b]) * (1 if s else -1)
                w = K * math.log(rd + 1) / math.log(7) * 2.2 / (2.2 + max(dw, -400) * .001)
                elo[a] += w * (s - e); elo[b] -= w * (s - e)
                e = expected(fast[a] - fast[b])
                fast[a] += 2.5 * K * (s - e); fast[b] -= 2.5 * K * (s - e)
                em = expected(elo[a] - elo[b] + off[(a, m)] - off[(b, m)])
                off[(a, m)] += KM * (s - em); off[(b, m)] -= KM * (s - em)
                if pa and pb:
                    g = KP * math.log(rd + 1) / math.log(7)
                    for tab, k in ((pl, g), (pfast, 2.5 * g), (ptier, g * tw)):
                        e = expected(sum(tab[p] for p in pa) / len(pa) - sum(tab[p] for p in pb) / len(pb))
                        for p in pa:
                            tab[p] += k * (s - e)
                        for p in pb:
                            tab[p] -= k * (s - e)
                share = 13 / (26 - min(rd, 13)) if s else 1 - 13 / (26 - min(rd, 13))
                e = .5 + max(-.4, min(.4, (rr[a] - rr[b]) / 1000))
                rr[a] += KR * (share - e); rr[b] -= KR * (share - e)
                if pa and pb:
                    e = .5 + max(-.4, min(.4, (sum(prr[p] for p in pa) / len(pa) - sum(prr[p] for p in pb) / len(pb)) / 1000))
                    for p in pa:
                        prr[p] += KR * (share - e)
                    for p in pb:
                        prr[p] -= KR * (share - e)
                for r in (pa, pb):
                    if r:
                        for p in r:
                            pm[p] += 1
                            pms[p] += tier >= 2
                            v, last = pact.get(p, (0.0, today))
                            pact[p] = (v * math.exp(-(today - last).days / 120) + 1, today)
                        for x, y in combinations(sorted(r), 2):
                            pair[(x, y)] += 1
                last10[a].append(s); last10[b].append(1 - s)
                lvl[a].append(tier); lvl[b].append(tier)
                n[a] += 1; n[b] += 1
                if trace:
                    trace(dict(day=today, page=page, tier=tier, a=a, b=b, map=m, won=s, diff=rd, exp=e0,
                               elo_a=elo[a], elo_b=elo[b], pa=pa, pb=pb, pl=pl))
            if bo3_maps:
                dec[a].append(bo3_maps == 3); dec[b].append(bo3_maps == 3)
            for x, r in ((a, ra), (b, rb)):
                seen[x] = today
                if r:
                    prev[x] = set(r["players"])
            for x in (a, b):
                cur = cur_rosters.get((page, x))
                if cur and (not hist[x] or hist[x][-1][0] != page):
                    hist[x].append((page, cur))
        pending.clear()

    def act_now(p, day):
        v, last = pact.get(p, (0.0, None))
        return v * math.exp(-(date.fromisoformat(day) - last).days / 120) if last else 0.0

    for gi, key in enumerate(data.order):
        if key[0] != curday:
            flush(); curday = key[0]
        ms = data.series[key]
        a, b = ms[0]["team1"], ms[0]["team2"]
        raw = {ms[0]["team1"]: ms[0]["raw1"], ms[0]["team2"]: ms[0]["raw2"]}
        if rng.random() < .5:
            a, b = b, a
        page = ms[0]["page"]
        ev = data.events.get(page, {})
        tier = ev.get("tier") or 1; lan = ev.get("lan") or 0.0; qual = ev.get("qual", 0)
        ro = ev.get("own", {}) if qual else ev.get("rosters", {})

        def roster(t):
            cur = next((ro[c] for c in (norm(t), norm(raw[t])) if c in ro), None)
            cur_rosters[(page, t)] = cur
            if not lag:
                return cur
            return next((r for pg, r in reversed(hist[t]) if pg != page), None)   # strictly an earlier event

        ra, rb = roster(a), roster(b)
        if not (ra and rb):                         # one known roster must not act as a signal
            ra = rb = None
        stats["both rosters"] += bool(ra and rb)
        side = {}
        for t, r in ((a, ra), (b, rb)):
            if r:
                ps = r["players"]
                for p in ps:
                    for tab in (pl, pfast, ptier):
                        tab.setdefault(p, elo[t])           # a new player starts at the team's rating
                    prr.setdefault(p, rr[t])
                c = len(ps)
                pairs = list(combinations(sorted(ps), 2))
                side[t] = dict(mean=sum(pl[p] for p in ps) / c, fast=sum(pfast[p] for p in ps) / c,
                               tier=sum(ptier[p] for p in ps) / c, top=max(pl[p] for p in ps), low=min(pl[p] for p in ps),
                               keep=len(set(ps) & prev[t]) / c if t in prev else 1.0, loans=r["loans"],
                               exp=sum(math.log1p(pm[p]) for p in ps) / c,
                               chem=sum(math.log1p(pair[q]) for q in pairs) / max(len(pairs), 1),
                               new=sum(pm[p] < 20 for p in ps) / c, known=True, rs=sum(prr[p] for p in ps) / c,
                               exps=sum(math.log1p(pms[p]) for p in ps) / c,
                               act=sum(math.log1p(act_now(p, key[0])) for p in ps) / c)
            else:
                v = elo[t]
                side[t] = dict(mean=v, fast=v, tier=v, top=v, low=v, keep=1.0, loans=0, exp=0, chem=0, new=0, known=False,
                               rs=rr[t], exps=0, act=0)
        A, B = side[a], side[b]
        both = A["known"] and B["known"]
        d, pd = elo[a] - elo[b], A["mean"] - B["mean"]
        fm = lambda x: (sum(last10[x]) + 2.5) / (len(last10[x]) + 5)
        tl = lambda x: (sum(lvl[x]) + 1.5 * 5) / (len(lvl[x]) + 5)
        today = date.fromisoformat(key[0])
        rest = lambda x: min((today - seen[x]).days, 30) if x in seen else 30
        stab = min(A["keep"], B["keep"])
        f = dict(elo=d, form=fm(a) - fm(b), pelo=pd,
                 level=tl(a) - tl(b), keep=A["keep"] - B["keep"], loans=A["loans"] - B["loans"],
                 elo_unstable=d * (1 - stab), pelo_unstable=pd * (1 - stab), elo_lan=d * lan, pelo_lan=pd * lan,
                 elo_s=d * (tier == 3), elo_b=d * (tier == 1), elo_qual=d * qual, unc=d / (1 + min(n[a], n[b]) / 30),
                 pfast=A["fast"] - B["fast"] - pd, rest=rest(a) - rest(b),
                 pexp=(A["exp"] - B["exp"]) * both, chem=(A["chem"] - B["chem"]) * both, newp=(A["new"] - B["new"]) * both,
                 ptop=(A["top"] - B["top"] - pd) * both, plow=(A["low"] - B["low"] - pd) * both,
                 ptier=A["tier"] - B["tier"] - pd, pcub=pd * abs(pd) / 400, rsh=rr[a] - rr[b], prs=A["rs"] - B["rs"],
                 pexps=(A["exps"] - B["exps"]) * both, pact=(A["act"] - B["act"]) * both,
                 pconf=pd * min(A["exp"], B["exp"]) / 7 * both)
        res = []
        for r in ms:
            s1, s2 = int(r["score1"]), int(r["score2"])
            ours, theirs = (s1, s2) if r["team1"] == a else (s2, s1)
            s, m = int(ours > theirs), r["map"]
            res.append((m, s, abs(ours - theirs)))
            M.append(dict(month=key[0][:7], g=gi, y=s, elo=d, form=f["form"], fast=fast[a] - fast[b] - d, unc=f["unc"],
                          map_off=off[(a, m)] - off[(b, m)], pelo=pd, rest=f["rest"], pfast=f["pfast"]))
        wa = sum(s for _, s, _ in res); wb = len(res) - wa
        y1 = res[0][1]
        need = max(wa, wb)
        if wa == wb or need > 3 or wa + wb > 2 * need - 1:
            stats["dropped"] += 1
        else:
            bo = 2 * need - 1
            pa_now, pb_now = (ra["players"], rb["players"]) if ra and rb else (None, None)
            td = lambda x: (sum(dec[x]) + 4) / (len(dec[x]) + 10)
            row = dict(month=key[0][:7], day=key[0], g=gi, a=a, b=b, bo=bo, y=int(wa > wb), tier=tier, lan=lan, maps=wa + wb, wa=wa, wb=wb,
                       y1=y1, stab=stab, tend=(td(a) + td(b)) / 2, known=both, players_a=pa_now, players_b=pb_now)
            for k, v in f.items():
                row[k + "1"] = v if bo == 1 else 0.0
                row[k + "3"] = v if bo > 1 else 0.0
            S.append(row)
        pending.append((a, b, ra, rb, res, tier, page, today, wa + wb if need == 2 and wa != wb else None))
    flush()
    state = dict(elo=dict(elo), pl=dict(pl), pfast=dict(pfast), rr=dict(rr), prr=dict(prr), last10={k: list(v) for k, v in last10.items()},
                 seen={k: v.isoformat() for k, v in seen.items()}, maps_played=dict(pm), dec={k: list(map(int, v)) for k, v in dec.items()},
                 last_roster={k: v[-1][1]["players"] for k, v in hist.items() if v})
    return S, M, state, stats


def live_row(st, a, b, ra, rb, today, bo):
    """Features for an upcoming match from the final ratings. Mirrors build(), and a test holds it to that."""
    if not (ra and rb):
        ra = rb = None
    elo = lambda t: st["elo"].get(t, 1500.0)
    rr = lambda t: st["rr"].get(t, 0.0)
    mean = lambda tab, r, t, d: sum(st[tab].get(p, d(t)) for p in r) / len(r) if r else d(t)
    ex = lambda r: sum(math.log1p(st["maps_played"].get(p, 0)) for p in r) / len(r)
    fm = lambda x: (sum(st["last10"].get(x, [])) + 2.5) / (len(st["last10"].get(x, [])) + 5)
    rest = lambda x: min((today - date.fromisoformat(st["seen"][x])).days, 30) if x in st["seen"] else 30
    d = elo(a) - elo(b)
    pd = mean("pl", ra, a, elo) - mean("pl", rb, b, elo)
    f = dict(elo=d, form=fm(a) - fm(b), pelo=pd, rest=rest(a) - rest(b),
             pfast=mean("pfast", ra, a, elo) - mean("pfast", rb, b, elo) - pd,
             pexp=ex(ra) - ex(rb) if ra else 0.0, prs=mean("prr", ra, a, rr) - mean("prr", rb, b, rr),
             pconf=pd * min(ex(ra), ex(rb)) / 7 if ra else 0.0)
    row = dict(bo=bo)
    for k, v in f.items():
        row[k + "1"] = v if bo == 1 else 0.0
        row[k + "3"] = v if bo > 1 else 0.0
    return row


def fit(X, y, l2=1.0, sw=None):
    """Ridge logistic regression without intercept, so swapping the teams flips the odds."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    sw = np.ones(len(y)) if sw is None else np.asarray(sw, float)
    w = np.zeros(X.shape[1])
    for _ in range(6):
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (sw * (y - p)) - l2 * w
        H = (X * (sw * p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w))
        w = w + np.linalg.solve(H, g)
    return w


def month_index(m):
    return int(m[:4]) * 12 + int(m[5:7])


def month_folds(first="2025-01", last="2026-12"):
    out, i = [], month_index(first)
    while i <= month_index(last):
        out.append(f"{(i - 1) // 12}-{(i - 1) % 12 + 1:02d}"); i += 1
    return out


def walk(rows, names, folds=FOLDS, start="2024-04", half_life=None):
    """Expanding walk-forward. Each fold trains only on months before the fold."""
    X = np.array([[x[f] for f in names] for x in rows], float)
    y = np.array([x["y"] for x in rows], float)
    m = [x["month"] for x in rows]
    P = {}
    for lo, hi in zip(folds, folds[1:]):
        tr = np.array([start <= v < lo for v in m])
        sd = np.maximum(np.sqrt((X[tr] ** 2).mean(0)), 1e-9)
        sw = None
        if half_life:                               # newer months count more, age measured from the fold start
            sw = np.array([.5 ** ((month_index(lo) - month_index(v)) / half_life) for v, k in zip(m, tr) if k])
        w = fit(X[tr] / sd, y[tr], sw=sw)
        te = [i for i, v in enumerate(m) if lo <= v < hi]
        for i, p in zip(te, 1 / (1 + np.exp(-(X[te] / sd) @ w))):
            P[i] = float(p)
    return P


def final_weights(rows, names, start="2024-04"):
    tr = [x for x in rows if start <= x["month"]]
    X = np.array([[x[f] for f in names] for x in tr], float)
    sd = np.maximum(np.sqrt((X ** 2).mean(0)), 1e-9)
    return fit(X / sd, [x["y"] for x in tr]).tolist(), sd.tolist()


def score(P, rows, idx=None):
    idx = list(P) if idx is None else idx
    return (sum(ll(P[i], rows[i]["y"]) for i in idx) / len(idx), sum((P[i] - rows[i]["y"]) ** 2 for i in idx) / len(idx),
            sum((P[i] > .5) == (rows[i]["y"] == 1) for i in idx) / len(idx))


def gain(P0, P1, rows, idx, B=2000):
    """Log loss gain of P1 over P0, bootstrapped by series."""
    per, cnt = defaultdict(float), defaultdict(int)
    for i in idx:
        per[rows[i]["g"]] += ll(P0[i], rows[i]["y"]) - ll(P1[i], rows[i]["y"]); cnt[rows[i]["g"]] += 1
    ks = list(per); a = np.array([per[k] for k in ks]); c = np.array([cnt[k] for k in ks])
    rs = np.random.default_rng(7); res = []
    for _ in range(B):
        s = rs.integers(0, len(ks), len(ks))
        res.append(a[s].sum() / c[s].sum())
    res.sort()
    return float(a.sum() / c.sum()), float(res[int(.025 * B)]), float(res[int(.975 * B)])


def two(*f):
    return [x + s for x in f for s in "13"]


def calibration(pairs, edges=(.5, .6, .7, .8, .9, 1.0001)):
    """pairs: (favourite probability, favourite won). Returns mean predicted, actual and count per bin."""
    out = []
    for lo, hi in zip(edges, edges[1:]):
        v = [(p, t) for p, t in pairs if lo <= p < hi]
        if v:
            out.append(dict(pred=sum(p for p, _ in v) / len(v), actual=sum(t for _, t in v) / len(v), n=len(v)))
    return out


def compose(p, bo):
    """Series win chance from an equal, independent chance on each map."""
    return p if bo == 1 else p * p * (3 - 2 * p) if bo == 3 else p ** 3 * (10 - 15 * p + 6 * p * p)


def devig(pa, pb):
    return (1 / pa) / (1 / pa + 1 / pb)


def match_odds(S, alias, odds):
    """Pair each odds row with one series on the same day, or one day either side."""
    lookup = defaultdict(set)
    for raw, canon in alias.items():
        lookup[norm(raw)].add(canon); lookup[norm(canon)].add(canon)
    byday = defaultdict(list)
    for i, x in enumerate(S):
        byday[x["day"]].append(i)
    out, used, miss = [], set(), Counter()
    for o in sorted(odds, key=lambda o: o["start"]):
        t1, t2 = lookup.get(norm(o["team1"]), set()), lookup.get(norm(o["team2"]), set())
        if not t1 or not t2:
            miss["unknown team"] += 1
            continue
        day = date.fromisoformat(o["start"][:10])
        hit = None
        for shift in (0, 1, -1):
            c = [i for i in byday[date.fromordinal(day.toordinal() + shift).isoformat()] if i not in used and
                 ((S[i]["a"] in t1 and S[i]["b"] in t2) or (S[i]["a"] in t2 and S[i]["b"] in t1))]
            if c:
                hit = c[0]
                break
        if hit is None:
            miss["series not in data"] += 1
            continue
        used.add(hit)
        p1, p2 = float(o["price1"]), float(o["price2"])
        pa, pb = (p2, p1) if S[hit]["a"] in t2 else (p1, p2)
        out.append(dict(i=hit, pa=pa, pb=pb, limit=float(o["limit"] or 0), tournament=o["tournament"], fid=o.get("fixture_id"), flip=S[hit]["a"] in t2))
    return out, miss
