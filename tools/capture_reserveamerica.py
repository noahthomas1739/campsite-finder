"""Save raw ReserveAmerica pages so a Texas State Parks scraper can be built against real markup.

Run from the repo root:
    python3 tools/capture_reserveamerica.py

Writes samples/reserveamerica/*.html plus index.txt (status, size, final URL for each).
Only a handful of requests are made, one at a time.
"""

import http.cookiejar
import os
import time
import urllib.error
import urllib.parse
import urllib.request

PARK_ID = 1200125  # Tyler State Park
SLUG = "tyler-state-park"
ARRIVAL = "10/23/2026"
NIGHTS = 1

BASE = "https://texasstateparks.reserveamerica.com"
OUT = os.path.join("samples", "reserveamerica")

# The park page is fetched first so the session cookies it sets are reused by the
# search URLs. Those are the URL shapes ReserveAmerica sites have used over the years;
# whichever one returns a site list is the one the scraper will use.
REQUESTS = [
    ("park_details", "GET", f"/camping/{SLUG}/r/campgroundDetails.do",
     {"contractCode": "TX", "parkId": PARK_ID}),
    ("campsite_search_get", "GET", f"/camping/{SLUG}/r/campsiteSearch.do",
     {"contractCode": "TX", "parkId": PARK_ID, "arvdate": ARRIVAL, "lengthOfStay": NIGHTS, "siteTypeFilter": "ALL"}),
    ("campsite_search_post", "POST", "/campsiteSearch.do",
     {"contractCode": "TX", "parkId": PARK_ID, "arvdate": ARRIVAL, "lengthOfStay": NIGHTS,
      "siteTypeFilter": "ALL", "submitSiteForm": "true", "search": "site", "currentMaximumWindow": "12"}),
    ("campsite_calendar", "GET", "/campsiteCalendar.do",
     {"page": "calendar", "contractCode": "TX", "parkId": PARK_ID, "calarvdate": ARRIVAL, "sitepage": "true", "startIdx": 0}),
    ("explore_page", "GET", f"https://www.reserveamerica.com/explore/{SLUG}/TX/{PARK_ID}/campsites",
     {"arrivalDate": "2026-10-23", "lengthOfStay": NIGHTS}),
]

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def main():
    os.makedirs(OUT, exist_ok=True)
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    index = []
    for name, method, path, params in REQUESTS:
        url = path if path.startswith("http") else BASE + path
        query = urllib.parse.urlencode(params)
        if method == "GET":
            req = urllib.request.Request(f"{url}?{query}", headers=HEADERS)
        else:
            req = urllib.request.Request(url, data=query.encode(), method="POST", headers=dict(
                HEADERS, **{"Content-Type": "application/x-www-form-urlencoded"}))
        try:
            with opener.open(req, timeout=30) as resp:
                status, final, body = resp.status, resp.geturl(), resp.read()
        except urllib.error.HTTPError as e:
            status, final, body = e.code, e.geturl(), e.read()
        except Exception as e:  # keep going; the error itself is useful to see
            status, final, body = "ERROR", url, repr(e).encode()
        with open(os.path.join(OUT, f"{name}.html"), "wb") as f:
            f.write(body)
        line = f"{name}\t{method}\t{status}\t{len(body)} bytes\t{final}"
        index.append(line)
        print(line)
        time.sleep(2)
    with open(os.path.join(OUT, "index.txt"), "w") as f:
        f.write("\n".join(index) + "\n")
    print(f"\nSaved to {OUT}/")


if __name__ == "__main__":
    main()
