"""Price the upcoming matches found in cached Liquipedia pages and keep a record of what was said before each match.

Reads the page cache written by cs2_liquipedia_maps.py. A match is priced while its start is still ahead; its row in
forward_log.csv is the last price computed before the start and is never changed afterwards.
Usage: python cs2_upcoming.py <cache.jsonl>   (writes dashboard/expert_upcoming.js and forward_log.csv)
"""
import csv, json, os, re, sys
from datetime import datetime, timedelta, timezone

import cs2_core as c
import cs2_model as M

OUT, LOG = "dashboard/expert_upcoming.js", "forward_log.csv"
FIELDS = ["logged_at", "start", "day", "event", "team_a", "team_b", "bo", "p_a", "data_through"]
AHEAD_DAYS, SHOWN_RESULTS, MIN_SERIES = 7, 15, 5
MONTHS = {m: i + 1 for i, m in enumerate("January February March April May June July August September October November December".split())}
# Hours ahead of UTC for the time zone templates Liquipedia uses in match dates.
ZONES = dict(UTC=0, GMT=0, WET=0, WEST=1, BST=1, CET=1, CEST=2, EET=2, EEST=3, MSK=3, TRT=3, AST=3, GST=4, PKT=5, IST=5.5, ICT=7,
             WIB=7, SGT=8, HKT=8, PHT=8, AWST=8, KST=9, JST=9, AEST=10, AEDT=11, NZST=12, NZDT=13, BRT=-3, ART=-3, EDT=-4, EST=-5,
             CDT=-5, CST=-6, MDT=-6, MST=-7, PDT=-7, PST=-8)


def blocks(text):
    for m in re.finditer(r"\{\{Match\b", text):
        depth, j = 0, m.start()
        while j < len(text) - 1:
            two = text[j:j + 2]
            if two == "{{":
                depth += 1; j += 2
            elif two == "}}":
                depth -= 1; j += 2
                if depth == 0:
                    yield text[m.start():j]
                    break
            else:
                j += 1


def start_time(block):
    """Start in UTC and the local day as written, or None when the date has no time or an unknown time zone."""
    m = re.search(r"\|\s*date\s*=\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})\s*-\s*(\d{1,2}):(\d{2})\s*\{\{Abbr/(\w+)", block)
    if m and m.group(1) in MONTHS and m.group(6).upper() in ZONES:
        local = datetime(int(m.group(3)), MONTHS[m.group(1)], int(m.group(2)), int(m.group(4)), int(m.group(5)))
        return (local - timedelta(hours=ZONES[m.group(6).upper()])).replace(tzinfo=timezone.utc), local.date()


def upcoming(pages, now, alias):
    """Unplayed matches with two known teams that start within AHEAD_DAYS. pages: title -> wikitext."""
    out = {}
    for title, text in pages.items():
        for b in blocks(text):
            teams = re.findall(r"\|\s*opponent[12]\s*=\s*\{\{TeamOpponent\s*\|\s*(?:template\s*=\s*)?([^|}]*)", b)
            (start, day), slots = start_time(b) or (None, None), len(set(re.findall(r"\|\s*map(\d)\s*=", b)))
            done = re.search(r"\|\s*finished\s*=[ \t]*\w", b) or re.search(r"\|\s*(?:winner|t[12]c?t)\s*=\s*\d", b)
            if len(teams) != 2 or not start or done or not slots or not now < start <= now + timedelta(days=AHEAD_DAYS):
                continue
            a, b2 = (alias.get(t.strip()) for t in teams)
            if a and b2 and a != b2:
                key = (start, frozenset((a, b2)))
                out.setdefault(key, dict(start=start, day=day, a=a, b=b2, bo=slots, event=title.replace("/", " ")))
    return sorted(out.values(), key=lambda x: (x["start"], x["a"]))


def price(model, state, x):
    """Chance of team a. Both teams need MIN_SERIES rated series; rosters are the last known ones."""
    if min(len(state["last10"].get(t, [])) for t in (x["a"], x["b"])) < MIN_SERIES:
        return None
    ra, rb = state["last_roster"].get(x["a"]), state["last_roster"].get(x["b"])
    return float(M.predict(model, [c.live_row(state, x["a"], x["b"], ra, rb, x["day"], x["bo"])])[0])


def merge_log(old, priced, now, through):
    """Rows of matches that already started stay as they are; rows of matches still ahead take the current price."""
    iso = lambda t: t.strftime("%Y-%m-%dT%H:%MZ")
    key = lambda r: (r["start"], frozenset((r["team_a"], r["team_b"])))
    rows = {key(r): r for r in old if r["start"] <= iso(now)}
    for x, p in priced:
        r = dict(logged_at=iso(now), start=iso(x["start"]), day=x["day"].isoformat(), event=x["event"], team_a=x["a"], team_b=x["b"], bo=str(x["bo"]),
                 p_a=f"{p:.4f}", data_through=through)
        rows[key(r)] = r
    return sorted(rows.values(), key=lambda r: (r["start"], r["team_a"]))


def settle(log, series):
    """Attach the result to logged matches that have one: the same two teams on the same day."""
    played = {(x["day"], frozenset((x["a"], x["b"]))): x for x in series}
    out = []
    for r in log:
        x = played.get((r["day"], frozenset((r["team_a"], r["team_b"]))))
        if x:
            out.append(dict(r, won_a=int(x["y"] if x["a"] == r["team_a"] else 1 - x["y"])))
    return out


def main():
    now = datetime.now(timezone.utc)
    pages = {}
    for line in open(sys.argv[1], encoding="utf8"):
        p = json.loads(line)
        pages[p["title"]] = p["text"]
    D = c.load_data()
    S, _, state, _ = c.build(D)
    model = M.fit_model([x for x in S if M.TRAIN_START <= x["month"]])
    through = S[-1]["day"]
    priced = [(x, p) for x in upcoming(pages, now, D.alias) if (p := price(model, state, x)) is not None]
    old = list(csv.DictReader(open(LOG, encoding="utf8"))) if os.path.exists(LOG) else []
    log = merge_log(old, priced, now, through)
    with open(LOG, "w", newline="", encoding="utf8") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader(); w.writerows(log)
    done = settle(log, S)
    record = None
    if done:
        ps = [float(r["p_a"]) for r in done]
        record = dict(n=len(done), logloss=sum(c.ll(p, r["won_a"]) for p, r in zip(ps, done)) / len(done),
                      accuracy=sum((p >= .5) == bool(r["won_a"]) for p, r in zip(ps, done)) / len(done))
    row = lambda r: [r["start"], r["event"], r["team_a"], r["team_b"], int(r["bo"]), float(r["p_a"])]
    result = dict(made=now.strftime("%Y-%m-%dT%H:%MZ"), through=through,
                  matches=[row(r) for r in log if r["start"] > now.strftime("%Y-%m-%dT%H:%MZ")],
                  record=record, results=[row(r) + [r["won_a"]] for r in done[-SHOWN_RESULTS:][::-1]])
    with open(OUT, "w", encoding="utf8") as f:
        f.write("window.CS2_UPCOMING = " + json.dumps(result, ensure_ascii=False, separators=(",", ":")) + ";\n")
    print("data through", through, "upcoming", len(result["matches"]), "logged", len(log), "settled", len(done))


if __name__ == "__main__":
    main()
