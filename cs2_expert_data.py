"""Aggregate team, player and map trends for the game-expert dashboard.

Team and player ratings here use Liquipedia map results and event rosters only.
Usage: .venv/Scripts/python cs2_expert_data.py   (writes dashboard/expert_data.js)
"""
import json, math
from bisect import bisect_right
from collections import Counter, defaultdict
from datetime import date, timedelta

import cs2_core as c

OUT = "dashboard/expert_data.js"
TOP_TEAMS, TOP_PLAYERS, ACTIVE_DAYS, MIN_RECENT_MAPS = 30, 60, 60, 10
HISTORY_DAYS, RECENT_DAYS, MOVE_DAYS, AFTER_DAYS, MIN_AFTER_MAPS = 548, 180, 365, 60, 10
META_MONTHS, MIN_MAP_TOTAL = 19, 20
CANON = {"Dust 2": "Dust II"}


def back(day, days):
    return day - timedelta(days=days)


def value_at(hist, day):
    """Last value on or before day, or None."""
    i = bisect_right([h[0] for h in hist], day)
    return hist[i - 1][1] if i else None


def share_rows(rows, months):
    maps = Counter(r["map"] for r in rows)
    keep = [m for m, n in maps.most_common() if n >= MIN_MAP_TOTAL]
    totals = [sum(r["month"] == m for r in rows) for m in months]
    cells = {m: [sum(r["month"] == mo and r["map"] == m for r in rows) for mo in months] for m in keep}
    return keep, totals, cells


def character(rows):
    """Round margins and how often the Elo favourite wins, against what Elo expected."""
    n = len(rows)
    if not n:
        return None
    won = sum(r["won"] if r["exp"] >= .5 else 1 - r["won"] for r in rows)
    ps = [max(r["exp"], 1 - r["exp"]) for r in rows]
    ci = 1.96 * math.sqrt(sum(p * (1 - p) for p in ps)) / n
    return dict(n=n, close=sum(r["diff"] <= 3 for r in rows) / n, margin=sum(r["diff"] for r in rows) / n,
                fav=won / n, expected=sum(ps) / n, ci=ci)


def main():
    maps, team_elo, player_hist, player_maps = [], defaultdict(list), defaultdict(list), Counter()
    events, player_last, player_team = defaultdict(dict), {}, {}

    def trace(t):
        day = t["day"]
        maps.append(dict(day=day, month=day.isoformat()[:7], tier=t["tier"], a=t["a"], b=t["b"], map=CANON.get(t["map"], t["map"]),
                         won=t["won"], diff=t["diff"], exp=t["exp"]))
        team_elo[t["a"]].append((day, t["elo_a"])); team_elo[t["b"]].append((day, t["elo_b"]))
        for team, roster in ((t["a"], t["pa"]), (t["b"], t["pb"])):
            if roster:
                events[team].setdefault(t["page"], (day, sorted(roster)))
                for p in roster:
                    player_hist[p].append((day, t["pl"][p])); player_maps[p] += 1
                    player_last[p] = day; player_team[p] = team

    state = c.build(c.load_data(), trace=trace)[2]
    today = max(m["day"] for m in maps)
    for team, hist in team_elo.items():
        assert abs(hist[-1][1] - state["elo"][team]) < 1e-6, team
    for p, hist in player_hist.items():
        assert abs(hist[-1][1] - state["pl"][p]) < 1e-6, p

    # ---- teams ---------------------------------------------------------------------------
    per_team, recent_n = defaultdict(list), Counter()
    since = back(today, RECENT_DAYS)
    for m in maps:
        for team, won in ((m["a"], m["won"]), (m["b"], 1 - m["won"])):
            per_team[team].append((m["day"], m["map"], won))
            recent_n[team] += m["day"] >= since
    active = [t for t, h in team_elo.items() if h[-1][0] >= back(today, ACTIVE_DAYS) and recent_n[t] >= MIN_RECENT_MAPS]
    active.sort(key=lambda t: -team_elo[t][-1][1])
    top = active[:TOP_TEAMS]

    def weekly(hist, first):
        out = {}
        for day, v in hist:
            if day >= first:
                out[day - timedelta(days=day.weekday())] = (day, v)
        return [[d.isoformat(), round(v, 1)] for d, v in out.values()]

    def moves_for(team):
        seq = sorted(events[team].values())
        hist = team_elo[team]
        out = []
        for i in range(1, len(seq)):
            day, cur = seq[i]
            if day < back(today, MOVE_DAYS):
                continue
            old, cur_set = set(seq[i - 1][1]), set(cur)
            nxt = set(seq[i + 1][1]) if i + 1 < len(seq) else None
            joined = sorted(p for p in cur_set - old if nxt is None or p in nxt)
            left = sorted(p for p in old - cur_set if nxt is None or p not in nxt)
            if not joined and not left:
                continue
            before = value_at(hist, back(day, 1))
            until = day + timedelta(days=AFTER_DAYS)
            n_after = sum(day <= d <= until for d, _ in hist)
            after = value_at(hist, until) if n_after >= MIN_AFTER_MAPS and until <= today else None
            out.append(dict(day=day.isoformat(), team=team, joined=joined, left=left, before=round(before, 1) if before is not None else None,
                            after=round(after, 1) if after is not None else None, n_after=n_after, confirmed=nxt is not None))
        return out

    prev_since, first = back(since, RECENT_DAYS), back(today, HISTORY_DAYS)
    teams = []
    for rank, team in enumerate(top, 1):
        hist = team_elo[team]
        cur = hist[-1][1]
        d30, d90 = value_at(hist, back(today, 30)), value_at(hist, back(today, 90))
        rec, old = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        for day, m, won in per_team[team]:
            tab = rec if day >= since else old if day >= prev_since else None
            if tab is not None:
                tab[m][0] += won; tab[m][1] += 1
        table = [dict(map=m, w=v[0], n=v[1], old_w=old[m][0], old_n=old[m][1]) for m, v in rec.items()]
        table.sort(key=lambda x: -(x["w"] + 2) / (x["n"] + 4))
        form = state["last10"].get(team, [])
        roster = (state["last_roster"].get(team) or [])
        teams.append(dict(name=team, rank=rank, elo=round(cur, 1), d30=round(cur - d30, 1) if d30 is not None else None,
                          d90=round(cur - d90, 1) if d90 is not None else None, form=[sum(form), len(form)], last=hist[-1][0].isoformat(),
                          hist=weekly(hist, first), maps=table, moves=moves_for(team),
                          roster=sorted(({"p": p, "r": round(state["pl"][p], 1), "maps": player_maps[p]} for p in roster if p in state["pl"]), key=lambda x: -x["r"])))

    # ---- players -------------------------------------------------------------------------
    cand = [p for p, d in player_last.items() if d >= back(today, ACTIVE_DAYS) and player_maps[p] >= 50]
    cand.sort(key=lambda p: -player_hist[p][-1][1])
    players = []
    for rank, p in enumerate(cand[:TOP_PLAYERS], 1):
        hist = player_hist[p]
        cur, d90 = hist[-1][1], value_at(hist, back(today, 90))
        monthly = {}
        for day, v in hist:
            if day >= back(today, 365):
                monthly[day.isoformat()[:7]] = round(v, 1)
        players.append(dict(rank=rank, p=p, team=player_team[p], r=round(cur, 1), d90=round(cur - d90, 1) if d90 is not None else None,
                            maps=player_maps[p], spark=list(monthly.values())))

    # ---- map pool ------------------------------------------------------------------------
    y, mo = today.year, today.month
    months = []
    for _ in range(META_MONTHS):
        months.insert(0, f"{y}-{mo:02d}")
        mo -= 1
        if mo == 0:
            y, mo = y - 1, 12
    full = months[:-1] if today.day < 25 else months
    recent3, prev3 = full[-3:], full[-6:-3]
    meta = {}
    for key, keep_tier in (("all", lambda t: True), ("s", lambda t: t == 3)):
        pool = [m for m in maps if keep_tier(m["tier"]) and m["month"] >= months[0]]
        names, totals, cells = share_rows(pool, months)
        shift = []
        for name in names:
            ix3, ixp = [months.index(x) for x in recent3], [months.index(x) for x in prev3]
            a, b = sum(cells[name][i] for i in ix3), sum(cells[name][i] for i in ixp)
            ta, tb = sum(totals[i] for i in ix3), sum(totals[i] for i in ixp)
            if ta and tb:
                shift.append(dict(map=name, recent=a / ta, prev=b / tb, n_recent=a, n_prev=b))
        shift.sort(key=lambda x: x["prev"] - x["recent"])
        window = [m for m in maps if keep_tier(m["tier"]) and m["day"] >= since]
        names_recent = [n for n, k in Counter(m["map"] for m in window).most_common() if k >= MIN_MAP_TOTAL]
        chars = [dict(map=n, **character([m for m in window if m["map"] == n])) for n in names_recent]
        meta[key] = dict(maps=names, totals=totals, cells=cells, shift=shift, recent_months=recent3, prev_months=prev3,
                         character=chars, overall=character(window))

    moves = sorted((m for t in teams for m in t["moves"]), key=lambda m: m["day"], reverse=True)
    out = dict(asof=today.isoformat(), maps_total=len(maps), months=months, partial_month=months[-1] if months[-1] not in full else None,
               recent_days=RECENT_DAYS, after_days=AFTER_DAYS, meta=meta, teams=teams, players=players, moves=moves)
    with open(OUT, "w", encoding="utf8") as f:
        f.write("window.CS2_EXPERT = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("as of", out["asof"], "maps", out["maps_total"], "teams", len(teams), "players", len(players), "moves", len(moves))
    print("top 10:", [(t["name"], round(t["elo"])) for t in teams[:10]])
    print("players:", [(p["p"], round(p["r"])) for p in players[:10]])
    print("pool:", {k: v["maps"] for k, v in meta.items()})
    print("shift:", [(s["map"], round(s["prev"] * 100, 1), round(s["recent"] * 100, 1)) for s in meta["all"]["shift"]])
    print("overall:", meta["all"]["overall"])


if __name__ == "__main__":
    main()
