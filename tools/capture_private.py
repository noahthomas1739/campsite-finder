"""Save real Campspot and Hipcamp pages so private-campground lookups can be built against them.

Run from the repo root, then push the samples folder:
    python3 tools/capture_private.py              # everything
    python3 tools/capture_private.py campspot     # just the Campspot pages

Writes samples/private/*.html|json plus index.txt and findings.txt. About 20 requests,
one at a time, with pauses between them.
"""

import http.cookiejar
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

OUT = os.path.join("samples", "private")
CHECKIN, CHECKOUT = "2026-11-27", "2026-11-29"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

START = [
    ("campspot_near_canyon_lake", "https://www.campspot.com/c/camping-in-texas/near-canyon-lake"),
    ("campspot_park_fimfo", "https://www.campspot.com/park/camp-fimfo"),
    ("hipcamp_canyon_lake",
     f"https://www.hipcamp.com/en-US/d/united-states/texas/canyon-lake/camping/all?arrive={CHECKIN}&depart={CHECKOUT}"),
    ("hipcamp_johnson_city",
     f"https://www.hipcamp.com/en-US/d/united-states/texas/johnson-city/camping/all?arrive={CHECKIN}&depart={CHECKOUT}"),
]

# Pages can embed the site's own API keys (e.g. a Mapbox token for its maps). They aren't
# needed for parsing, and GitHub rightly refuses pushes containing them, so blank them out.
SECRET_PATTERNS = [
    re.compile(rb"\b(?:pk|sk|tk)\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),  # Mapbox
    re.compile(rb"\bAIza[0-9A-Za-z_-]{35}\b"),  # Google API keys
    re.compile(rb"\b(?:sk|pk|rk)_(?:live|test)_[0-9A-Za-z]{10,}\b"),  # Stripe
    re.compile(rb"\bgh[pousr]_[0-9A-Za-z]{30,}\b"),  # GitHub
    re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key IDs
]


def redact(body):
    for pattern in SECRET_PATTERNS:
        body = pattern.sub(b"REDACTED", body)
    return body


opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
index, findings = [], []


def get(name, url, ext="html"):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with opener.open(req, timeout=40) as resp:
            status, final, body = resp.status, resp.geturl(), resp.read()
    except urllib.error.HTTPError as e:
        status, final, body = e.code, e.geturl(), e.read()
    except Exception as e:
        status, final, body = "ERROR", url, repr(e).encode()
        # macOS's built-in Python can't speak the TLS version some sites require; curl can.
        if "SSL" in repr(e) and shutil.which("curl"):
            cmd = ["curl", "-sSL", "--compressed", "--max-time", "40", "-w", "\n%{http_code} %{url_effective}"]
            for k, v in HEADERS.items():
                cmd += ["-H", f"{k}: {v}"]
            out = subprocess.run(cmd + [url], capture_output=True)
            raw, _, tail = out.stdout.rpartition(b"\n")
            code, _, eff = tail.decode().partition(" ")
            status, final, body = f"{code} (curl)", eff or url, raw or out.stderr
    body = redact(body)
    with open(os.path.join(OUT, f"{name}.{ext}"), "wb") as f:
        f.write(body)
    line = f"{name}\t{status}\t{len(body)} bytes\t{final}"
    index.append(line)
    print(line)
    time.sleep(2)
    return body.decode("utf-8", "replace")


def note(label, items):
    items = sorted(set(items))
    findings.append(f"## {label} ({len(items)})")
    findings.extend(items[:80])
    findings.append("")


def main():
    os.makedirs(OUT, exist_ok=True)
    only = sys.argv[1] if len(sys.argv) > 1 else ""
    pages = {name: (get(name, url) if name.startswith(only) else "") for name, url in START}

    # Campspot: booking slugs linked from the listing and park pages.
    campspot_text = pages["campspot_near_canyon_lake"] + pages["campspot_park_fimfo"]
    book_slugs = re.findall(r"campspot\.com/book/([A-Za-z0-9_-]+)|\"/book/([A-Za-z0-9_-]+)", campspot_text)
    book_slugs = sorted({a or b for a, b in book_slugs})
    park_slugs = sorted(set(re.findall(r"/park/([A-Za-z0-9_-]+)", campspot_text)))
    note("campspot booking slugs", book_slugs)
    note("campspot park slugs", park_slugs)

    # Park pages with the stay dates filled in, as the page's own "Check Availability" form submits them.
    for slug in [p for p in park_slugs if p != "opengraph"][:6]:
        get(f"campspot_dates_{slug}",
            f"https://www.campspot.com/park/{slug}?checkin={CHECKIN}&checkout={CHECKOUT}&adults=2&children=0&pets=0")

    # Booking pages for a few parks, with the stay dates in the URL.
    for slug in book_slugs[:3]:
        get(f"campspot_book_{slug}", f"https://www.campspot.com/book/{slug}")
        get(f"campspot_search_{slug}",
            f"https://www.campspot.com/book/{slug}/search/{CHECKIN}/{CHECKOUT}/guests0,2,0/list?campsiteCategory=All")

    # The site's JavaScript names the APIs it calls; list the ones that look like availability lookups.
    api_urls, api_paths = set(), set()
    for name in [n for n in pages if pages[n]] + [n for n in os.listdir(OUT) if n.startswith("campspot_book_")]:
        text = pages.get(name) or open(os.path.join(OUT, name), encoding="utf-8", errors="replace").read()
        host = "https://www.hipcamp.com" if name.startswith("hipcamp") else "https://www.campspot.com"
        for src in re.findall(r'<script[^>]+src="([^"]+\.js[^"]*)"', text)[:25]:
            js_url = src if src.startswith("http") else host + src
            try:
                with opener.open(urllib.request.Request(js_url, headers=HEADERS), timeout=40) as r:
                    js = r.read().decode("utf-8", "replace")
            except Exception:
                if not shutil.which("curl"):
                    continue
                js = subprocess.run(["curl", "-sSL", "--compressed", "--max-time", "40", "-A", HEADERS["User-Agent"],
                                     js_url], capture_output=True).stdout.decode("utf-8", "replace")
            api_urls.update(re.findall(r'https://[A-Za-z0-9.-]*(?:api|insite)[A-Za-z0-9.-]*\.[a-z]+[A-Za-z0-9/_.{}$-]*', js))
            api_paths.update(re.findall(r'["\'`](/api/[A-Za-z0-9/_.{}$:-]{3,80})', js))
            time.sleep(0.5)
    note("API hosts/URLs seen in JavaScript", api_urls)
    note("API paths seen in JavaScript", api_paths)

    json_tag = re.compile(r'<script[^>]*type="application/json"[^>]*>|<script[^>]*id="__NEXT_DATA__"[^>]*>')
    for name, text in pages.items():
        if not text:
            continue
        tags = [re.search(r'id="([^"]+)"', t) for t in json_tag.findall(text)]
        note(f"embedded JSON script tags in {name}", [t.group(1) for t in tags if t])

    with open(os.path.join(OUT, "index.txt"), "w") as f:
        f.write("\n".join(index) + "\n")
    with open(os.path.join(OUT, "findings.txt"), "w") as f:
        f.write("\n".join(findings) + "\n")
    print(f"\nSaved to {OUT}/  ({len(book_slugs)} Campspot booking slugs, {len(api_urls)} API URLs found)")


if __name__ == "__main__":
    main()
