"""Texas State Parks, booked through ReserveAmerica.

There's no public API, but ReserveAmerica's campsite search page embeds its results
as JSON (<script id="initialState">): every site with its type, loop, hookups and a
night-by-night availabilityGrid starting at the arrival date. Results come 20 per
page, selected with ?pageNumber=N (0-based).

Park IDs come from the parkId= parameter on each park's ReserveAmerica page.
Coordinates are approximate park locations, used only for distance filtering.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import timedelta
from string import capwords

from .filters import is_specialty

BASE = "https://www.reserveamerica.com"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}
MAX_PAGES = 15  # safety cap; the biggest park here has ~7 pages of 20 sites


@dataclass
class StatePark:
    name: str
    slug: str
    park_id: int
    lat: float
    lon: float
    notes: str = ""

    def url(self, check_in=None, nights=None):
        url = f"{BASE}/explore/{self.slug}/TX/{self.park_id}/campsites"
        if check_in:
            url += "?" + urllib.parse.urlencode({"arrivalDate": check_in.isoformat(), "lengthOfStay": nights})
        return url


@dataclass
class StateParkSite:
    name: str
    loop: str
    site_type: str
    electric_amps: str = ""
    rate: str = ""


@dataclass
class StateParkResult:
    park: StatePark
    distance_mi: float
    sites: list = field(default_factory=list)
    error: str | None = None


# East / northeast of Dallas-Fort Worth, roughly 1-2.5 hours out.
PARKS = [
    StatePark("Lake Tawakoni State Park", "lake-tawakoni-state-park", 1200120, 32.84, -95.99,
              notes="full hookup + electric sites"),
    StatePark("Purtis Creek State Park", "purtis-creek-state-park", 1200122, 32.35, -95.99,
              notes="electric sites; small no-wake fishing lake"),
    StatePark("Cooper Lake State Park - South Sulphur", "cooper-lake-state-park-south-sulphur", 1200116, 33.27, -95.64,
              notes="50-amp electric sites"),
    StatePark("Cooper Lake State Park - Doctors Creek", "cooper-lake-state-park-doctors-creek", 1200115, 33.33, -95.71),
    StatePark("Tyler State Park", "tyler-state-park", 1200125, 32.48, -95.29,
              notes="full hookup + water/electric (50-amp) sites"),
    StatePark("Lake Bob Sandlin State Park", "lake-bob-sandlin-state-park", 1200119, 33.05, -95.00,
              notes="electric sites"),
    StatePark("Daingerfield State Park", "daingerfield-state-park", 1200117, 33.01, -94.70,
              notes="full hookup sites"),
    # Around DFW itself, for --direction any.
    StatePark("Cedar Hill State Park", "cedar-hill-state-park", 1200114, 32.62, -96.98,
              notes="Joe Pool Lake, inside DFW"),
    StatePark("Eisenhower State Park", "eisenhower-state-park", 1200118, 33.81, -96.61,
              notes="Lake Texoma, north of DFW"),
]


def parse_search_page(page_html):
    """The searchResults object embedded in a ReserveAmerica campsite search page."""
    m = re.search(r'<script[^>]*id="initialState"[^>]*>(.*?)</script>', page_html, re.S)
    if not m:
        raise ValueError("ReserveAmerica page had no initialState data (blocked, or the page changed)")
    return json.loads(m.group(1))["backend"]["productSearch"]["searchResults"]


def _attribute(record, name):
    for attr in (record.get("details") or {}).get("attributes") or []:
        if attr.get("name") == name:
            values = attr.get("value") or []
            return str(values[0]) if values else ""
    return ""


def is_electric(record):
    group = (record.get("prodGrpName") or "").lower()
    if "electric" in group or "full hookup" in group:
        return "non" not in group
    # Other campsite groups (e.g. "Campsite with Water") can still list an amp rating.
    amps = _attribute(record, "Electricity Hookup")
    return "campsite" in group and amps not in ("", "0", "N", "No")


def is_open(record, check_in, check_out):
    """Available for every night from check_in up to check_out."""
    grid = {g.get("date"): g.get("status") for g in record.get("availabilityGrid") or []}
    nights = [(check_in + timedelta(days=i)).isoformat() for i in range((check_out - check_in).days)]
    return all(grid.get(n) == "AVAILABLE" for n in nights)


def open_sites(records, check_in, check_out, electric_only=False, standard_only=True):
    sites = []
    for r in records:
        if (r.get("prodInfo") or {}).get("typeOfUse") != "NIGHTLY":
            continue
        if standard_only and is_specialty(r.get("prodGrpName")):
            continue
        if electric_only and not is_electric(r):
            continue
        if not is_open(r, check_in, check_out):
            continue
        details = r.get("details") or {}
        sites.append(StateParkSite(
            name=r.get("name", ""),
            loop=capwords(details.get("loopName") or ""),
            site_type=r.get("prodGrpName", ""),
            electric_amps=_attribute(r, "Electricity Hookup"),
            rate=details.get("ratesStartingFrom") or "",
        ))
    return sites


def _fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=40) as resp:
        return resp.read().decode("utf-8", "replace")


def available_sites(park, check_in, check_out, electric_only=False, standard_only=True, fetch=None, delay=1.0):
    fetch = fetch or _fetch
    nights = (check_out - check_in).days
    base = park.url(check_in, nights)
    sites, page = [], 0
    while page < MAX_PAGES:
        results = parse_search_page(fetch(f"{base}&pageNumber={page}"))
        found = open_sites(results.get("records") or [], check_in, check_out, electric_only, standard_only)
        # The summary says whether anything at all is open for the stay; if not (and the
        # first page agrees), don't fetch the rest.
        if page == 0 and not found and (results.get("summary") or {}).get("atLeastOneSiteAvailable") is False:
            return []
        sites.extend(found)
        page += 1
        if page >= (results.get("totalPages") or 0):
            break
        time.sleep(delay)
    return sites
