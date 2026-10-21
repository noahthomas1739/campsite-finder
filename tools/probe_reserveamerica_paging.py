"""Find which URL parameter pages through ReserveAmerica campsite results.

Run from the repo root and paste the printed lines back:
    python3 tools/probe_reserveamerica_paging.py
"""

import json
import re
import time
import urllib.request

URL = "https://www.reserveamerica.com/explore/tyler-state-park/TX/1200125/campsites?arrivalDate=2026-10-23&lengthOfStay=1"
CANDIDATES = ["", "&pageNumber=1", "&page=1", "&currentPage=1", "&pageIndex=1", "&startIdx=20", "&startIndex=20"]
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def main():
    for extra in CANDIDATES:
        try:
            with urllib.request.urlopen(urllib.request.Request(URL + extra, headers=HEADERS), timeout=30) as r:
                page = r.read().decode("utf-8", "replace")
            m = re.search(r'id="initialState"[^>]*>(.*?)</script>', page, re.S)
            sr = json.loads(m.group(1))["backend"]["productSearch"]["searchResults"]
            first = sr["records"][0]["name"] if sr.get("records") else None
            print(f"{extra or '(none)':18} startIndex={sr.get('startIndex')} page={sr['control'].get('currentPage')} "
                  f"first={first} total={sr.get('totalRecords')}")
        except Exception as e:
            print(f"{extra or '(none)':18} ERROR {e!r}"[:200])
        time.sleep(2)

    # The page's own JavaScript names the API it calls for more results; list those paths too.
    try:
        with urllib.request.urlopen(urllib.request.Request(URL, headers=HEADERS), timeout=30) as r:
            page = r.read().decode("utf-8", "replace")
        found = set()
        for src in re.findall(r'<script[^>]+src="(/newra/js/[^"]+)"', page):
            with urllib.request.urlopen(urllib.request.Request("https://www.reserveamerica.com" + src, headers=HEADERS), timeout=30) as r:
                js = r.read().decode("utf-8", "replace")
            found.update(re.findall(r'["\'`](/jaxrs-json/[A-Za-z0-9/_${}.:-]{3,80})', js))
            time.sleep(0.5)
        print("API paths:", ", ".join(sorted(found)[:30]) or "none found")
    except Exception as e:
        print("API paths: ERROR", repr(e)[:150])


if __name__ == "__main__":
    main()
