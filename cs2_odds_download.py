"""Save the last pre-match Pinnacle Winner prices for top CS2 events from OddsPapi.

Reads ODDSPAPI_KEY. Keep the output private. Stops on any response other than 200, 404 or 429.
Usage: python cs2_odds_download.py <out.csv> [from] [to]
"""
import csv, json, os, sys, time, urllib.error, urllib.parse, urllib.request
from datetime import date, timedelta

out = sys.argv[1]
start = date.fromisoformat(sys.argv[2] if len(sys.argv) > 2 else "2026-04-25")
end = date.fromisoformat(sys.argv[3] if len(sys.argv) > 3 else "2026-11-06")
KEY = os.environ["ODDSPAPI_KEY"]
TOP = ("esl", "intel extreme", "iem", "blast", "pgl", "esports world cup", "starladder", "starseries", "major",
       "fissure", "cct", "thunderpick", "betboom", "skyesports", "roman imperium", "dust2", "exort", "united21")


def get(path, **q):
    q["apiKey"] = KEY
    req = urllib.request.Request("https://api.oddspapi.io/v4/" + path + "?" + urllib.parse.urlencode(q),
                                 headers={"User-Agent": "cs2-research"})
    for _ in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code != 429:
                sys.exit(f"stopping: HTTP {e.code} on {path}")
            time.sleep(30)
    sys.exit("stopping: repeated 429")


fixtures, d = {}, start
while d < end:
    e = min(d + timedelta(days=5), end)
    for x in get("fixtures", sportId=17, **{"from": d.isoformat(), "to": e.isoformat()}) or []:
        if x.get("statusId") == 2 and any(t in x.get("tournamentName", "").lower() for t in TOP):
            fixtures[x["fixtureId"]] = x
    d = e
    time.sleep(3)
print("fixtures", len(fixtures), flush=True)

done = set()
if os.path.exists(out):
    done = {r["fixture_id"] for r in csv.DictReader(open(out, encoding="utf8"))}
fields = ["fixture_id", "start", "team1", "team2", "tournament", "price1", "price2", "price_time", "limit"]
with open(out, "a", newline="", encoding="utf8") as f:
    w = csv.DictWriter(f, fields)
    if not done:
        w.writeheader()
    hits = 0
    for i, (fid, x) in enumerate(sorted(fixtures.items(), key=lambda kv: kv[1]["startTime"])):
        if fid in done:
            continue
        time.sleep(7)
        h = get("historical-odds", fixtureId=fid, bookmakers="pinnacle")
        if h:
            try:
                oc = h["bookmakers"]["pinnacle"]["markets"]["171"]["outcomes"]
                last = []
                for k in ("171", "172"):
                    pts = [p for p in oc[k]["players"]["0"] if p["createdAt"] < x["startTime"] and p.get("price")]
                    last.append(max(pts, key=lambda p: p["createdAt"]))
                w.writerow(dict(fixture_id=fid, start=x["startTime"], team1=x["participant1Name"], team2=x["participant2Name"],
                                tournament=x["tournamentName"], price1=last[0]["price"], price2=last[1]["price"],
                                price_time=max(p["createdAt"] for p in last), limit=last[0].get("limit")))
                f.flush()
                hits += 1
            except (KeyError, ValueError):
                pass
        if i % 50 == 0:
            print(f"{i}/{len(fixtures)} hits {hits}", flush=True)
print("done hits", hits, flush=True)
