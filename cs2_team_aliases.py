"""Resolve Liquipedia team template names to canonical team names.

Uses action=expandtemplates, paced at the stricter 30 s limit that applies to action=parse.
Usage: python cs2_team_aliases.py cs2_maps.csv team_aliases.json
"""
import csv, gzip, http.client, json, os, re, sys, time, urllib.parse

UA = "cs2-prematch-research/0.1 (%s)" % (open("contact.txt").read().strip() if os.path.exists("contact.txt") else "add contact.txt")
names = sorted({r[k] for r in csv.DictReader(open(sys.argv[1], encoding="utf8")) for k in ("team1", "team2")})
out = json.load(open(sys.argv[2], encoding="utf8")) if os.path.exists(sys.argv[2]) else {}
todo = [n for n in names if n not in out]
conn = http.client.HTTPSConnection("liquipedia.net", timeout=60)
for k in range(0, len(todo), 80):
    part = todo[k:k + 80]
    text = "".join(f"@@{i}@@{{{{Team|{n}}}}}" for i, n in enumerate(part))
    body = urllib.parse.urlencode({"action": "expandtemplates", "format": "json", "prop": "wikitext", "text": text})
    conn.request("POST", "/counterstrike/api.php", body, {"User-Agent": UA, "Accept-Encoding": "gzip",
                                                         "Content-Type": "application/x-www-form-urlencoded"})
    r = conn.getresponse()
    raw = r.read()
    if r.status != 200:
        sys.exit(f"stopping: HTTP {r.status}")
    wt = json.loads(gzip.decompress(raw) if r.getheader("Content-Encoding") == "gzip" else raw)["expandtemplates"]["wikitext"]
    chunks = re.split(r"@@(\d+)@@", wt)
    for i, chunk in zip(chunks[1::2], chunks[2::2]):
        m = re.search(r'data-highlighting-class="([^"]+)"', chunk)
        out[part[int(i)]] = m.group(1) if m else part[int(i)]
    json.dump(out, open(sys.argv[2], "w", encoding="utf8"), ensure_ascii=False, indent=0)
    print(f"{k + len(part)}/{len(todo)}", flush=True)
    time.sleep(30)
print("names", len(out), "canonical", len(set(out.values())), flush=True)
