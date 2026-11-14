"""Collect CS2 map results through the Liquipedia MediaWiki API.

Follows the API terms: one request per 2+ seconds, gzip, one reused connection, a project
User-Agent with contact details, local caching, no action=parse, no HTML pages.
Content is CC-BY-SA 3.0, credit Liquipedia as the source.
Usage: python cs2_liquipedia_maps.py <cache.jsonl> <out.csv>
"""
import csv, gzip, http.client, json, os, re, sys, time, urllib.parse

cache_path, out_path = sys.argv[1], sys.argv[2]
UA = "cs2-prematch-research/0.1 (%s)" % (open("contact.txt").read().strip() if os.path.exists("contact.txt") else "add contact.txt")
conn = http.client.HTTPSConnection("liquipedia.net", timeout=60)
last = [0.0]


def api(**p):
    wait = 2.3 - (time.time() - last[0])
    if wait > 0:
        time.sleep(wait)
    last[0] = time.time()
    q = urllib.parse.urlencode(dict(p, action="query", format="json"))
    conn.request("GET", "/counterstrike/api.php?" + q, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    r = conn.getresponse()
    body = r.read()
    if r.status != 200:
        sys.exit(f"stopping: HTTP {r.status}, nothing retried")
    return json.loads(gzip.decompress(body) if r.getheader("Content-Encoding") == "gzip" else body)


def members(cat):
    out, cont = [], {}
    while True:
        d = api(list="categorymembers", cmtitle=cat, cmlimit=500, cmnamespace=0, **cont)
        out += [m["title"] for m in d["query"]["categorymembers"]]
        if "continue" not in d:
            return out
        cont = {"cmcontinue": d["continue"]["cmcontinue"]}


def subpages(root):
    d = api(list="allpages", apprefix=root + "/", aplimit=100, apnamespace=0)
    return [p["title"] for p in d["query"]["allpages"]]


done = set()
if os.path.exists(cache_path):
    for line in open(cache_path, encoding="utf8"):
        done.add(json.loads(line)["title"])
roots = []
for cat in ("Category:S-Tier Tournaments", "Category:A-Tier Tournaments", "Category:B-Tier Tournaments"):
    m = members(cat)
    print(cat, len(m), flush=True)
    roots += m
roots = sorted({t for t in roots if re.search(r"20(23|24|25|26)", t)})
print("roots", len(roots), flush=True)

with open(cache_path, "a", encoding="utf8") as cache:
    for i, root in enumerate(roots):
        titles = [t for t in [root] + subpages(root) if t not in done]
        for k in range(0, len(titles), 5):
            d = api(prop="revisions", rvprop="content", rvslots="main", titles="|".join(titles[k:k + 5]))
            for p in d["query"]["pages"].values():
                text = p.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
                if "{{Map" in text:
                    cache.write(json.dumps({"title": p["title"], "text": text}) + "\n")
                done.add(p.get("title"))
            cache.flush()
        if i % 25 == 0:
            print(f"root {i}/{len(roots)}", flush=True)


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


MONTHS = {m: i + 1 for i, m in enumerate("January February March April May June July August September October November December".split())}


def when(s):
    m = re.search(r"\|\s*date\s*=\s*(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return "-".join(m.groups())
    m = re.search(r"\|\s*date\s*=\s*([A-Z][a-z]+)\s+(\d{1,2}),\s*(\d{4})", s)
    if m and m.group(1) in MONTHS:
        return f"{m.group(3)}-{MONTHS[m.group(1)]:02d}-{int(m.group(2)):02d}"


num = lambda s, k: sum(int(x) for x in re.findall(r"\|\s*" + k + r"\s*=\s*(\d+)", s))
seen, rows = set(), 0
with open(out_path, "w", newline="", encoding="utf8") as f:
    w = csv.writer(f)
    w.writerow(["date", "team1", "team2", "map_no", "map", "score1", "score2", "page"])
    for line in open(cache_path, encoding="utf8"):
        page = json.loads(line)
        for b in blocks(page["text"]):
            t = re.findall(r"\|\s*opponent[12]\s*=\s*\{\{TeamOpponent\s*\|\s*(?:template\s*=\s*)?([^|}]+)", b)
            day = when(b)
            if len(t) != 2 or not day:
                continue
            for mp in re.finditer(r"\|\s*map(\d)\s*=\s*\{\{Map\s*\|(.*?)\}\}", b, re.S):
                body = mp.group(2)
                name = re.search(r"map\s*=\s*([^|\n}]+)", body)
                # Overtime rounds are o<period>t<team>t / o<period>t<team>ct on Liquipedia (o1t1t, o2t2ct ...).
                s1 = num(body, "t1t") + num(body, "t1ct") + num(body, r"o\d+t1(?:t|ct)")
                s2 = num(body, "t2t") + num(body, "t2ct") + num(body, r"o\d+t2(?:t|ct)")
                key = (day, t[0], t[1], mp.group(1))
                if name and name.group(1).strip() and s1 != s2 and s1 + s2 >= 13 and key not in seen and day >= "2023-10-01":
                    seen.add(key)
                    w.writerow([day, t[0].strip(), t[1].strip(), mp.group(1), name.group(1).strip(), s1, s2, page["title"]])
                    rows += 1
print("map rows", rows, flush=True)
