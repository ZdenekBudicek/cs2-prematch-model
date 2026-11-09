"""Extract event tier, LAN status and team rosters from the cached Liquipedia pages. No network.

Rosters are the event rosters on Liquipedia. Pages may be edited after an event, so a late stand-in
can appear on the page even if it was announced close to the match. This is noted in the model card.
Usage: python cs2_event_features.py lp_cache.jsonl cs2_events.json
"""
import json, re, sys

STOP = {"team", "esports", "esport", "gaming", "club", "gg", "e", "sports", "clan"}


def norm(s):
    s = re.sub(r"\(.*?\)", " ", s.lower())
    parts = [t for t in re.findall(r"[a-z0-9]+", s) if t not in STOP]
    return "".join(parts) or re.sub(r"\W", "", s)


def rosters(text):
    out = {}
    for chunk in re.split(r"\{\{TeamCard\s*\n", text)[1:]:
        t = re.search(r"\|\s*team\s*=\s*([^|\n}]+)", chunk)
        if not t:
            continue
        ps = [v.strip() for _, v in re.findall(r"\|\s*p(\d)\s*=\s*([^|\n}]+)", chunk.split("|inotes")[0]) if v.strip()]
        loans = len(re.findall(r"\|\s*p\dteam\s*=\s*[^|\n}]", chunk.split("|inotes")[0]))
        if len(ps) >= 3:
            out[norm(t.group(1))] = dict(players=ps[:6], loans=loans)
    for chunk in re.split(r"\{\{Opponent\|", text)[1:]:
        if "players={{Persons" not in chunk:
            continue
        name = re.match(r"\s*([^|\n}]+)", chunk)
        ps = []
        for body in re.findall(r"\{\{Person\|([^{}]*)\}\}", chunk):
            args = body.split("|")
            if any(a.startswith(("role=", "played=false", "results=false", "type=")) for a in args):
                continue
            first = [a for a in args if "=" not in a]
            if first:
                ps.append(first[0].strip())
        if name and len(ps) >= 3:
            out.setdefault(norm(name.group(1)), dict(players=ps[:6], loans=0))
    return out


def meta(text):
    d = {}
    t = re.search(r"\|\s*liquipediatier\s*=\s*([^|\n}]+)", text)
    if t:
        v = t.group(1).strip().lower()
        d["tier"] = 3 if v[:1] in ("1", "s") else 2 if v[:1] in ("2", "a") else 1
    q = re.search(r"\|\s*liquipediatiertype\s*=\s*([^|\n}]+)", text)
    d["qual"] = int(bool(q and "qualifier" in q.group(1).lower()))
    k = re.search(r"\|\s*type\s*=\s*([^|\n}]+)", text)
    if k:
        v = k.group(1).lower()
        d["lan"] = 1.0 if "offline" in v and "online" not in v else .5 if "offline" in v else 0.0
    return d


pages = {}
for line in open(sys.argv[1], encoding="utf8"):
    p = json.loads(line)
    pages[p["title"]] = dict(meta(p["text"]), rosters=rosters(p["text"]))
out = {}
for title, d in pages.items():
    parts = title.split("/")
    chain = [pages.get("/".join(parts[:k])) for k in range(len(parts) - 1, 0, -1)]
    r = dict(d, own=d["rosters"])                  # qualifiers must not inherit the main event's qualified teams
    for up in chain:
        if up:
            for key in ("tier", "lan"):
                r.setdefault(key, up.get(key))
            r["rosters"] = {**up["rosters"], **r["rosters"]}
    r["qual"] = int(d.get("qual", 0) or "qualifier" in title.lower())
    out[title] = r
json.dump(out, open(sys.argv[2], "w", encoding="utf8"), ensure_ascii=False)
n = len(out)
print("pages", n, "tier", sum("tier" in v and v["tier"] is not None for v in out.values()),
      "lan", sum(v.get("lan") is not None for v in out.values()), "with rosters", sum(bool(v["rosters"]) for v in out.values()))
