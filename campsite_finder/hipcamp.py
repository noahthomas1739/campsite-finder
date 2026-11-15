"""Private campgrounds listed on Hipcamp.

Hipcamp's town pages (/d/united-states/<state>/<town>/camping/all) embed their
listings as JSON in <script id="__NEXT_DATA__">: name, location, price, rating and
features such as "Electricity Hookup". Availability for specific dates isn't in the
page, so these are listed with a dated link to check, not as confirmed open sites.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from dataclasses import dataclass, field

from . import web

BASE = "https://www.hipcamp.com"
STATES = {"TX": "texas", "OK": "oklahoma", "LA": "louisiana", "NM": "new-mexico", "AR": "arkansas"}


@dataclass
class Land:
    name: str
    lat: float
    lon: float
    path: str
    city: str = ""
    category: str = ""
    accommodations: list = field(default_factory=list)
    features: list = field(default_factory=list)
    price: str = ""
    recommends_pct: int | None = None
    recommends_count: int = 0
    sites: int | None = None

    @property
    def electric(self):
        return "electricity-hookup" in self.features

    @property
    def lodging_only(self):
        """Cabins/glamping only: no tent or RV sites."""
        return bool(self.accommodations) and not ({"tent", "rv"} & set(self.accommodations))

    def url(self, check_in=None, check_out=None):
        if not check_in:
            return BASE + self.path
        return BASE + self.path + "?" + urllib.parse.urlencode(
            {"arrive": check_in.isoformat(), "depart": check_out.isoformat()})


@dataclass
class LandResult:
    land: Land
    distance_mi: float
    off_route_mi: float | None = None


def town_page(place):
    """'Canyon Lake, TX' -> Hipcamp town page URL, or None if the state isn't mapped."""
    town, _, state = (p.strip() for p in place.rpartition(","))
    state = STATES.get(state.upper())
    if not (town and state):
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", town.lower()).strip("-")
    return f"{BASE}/en-US/d/united-states/{state}/{slug}/camping/all"


def parse_town_page(page_html):
    m = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', page_html, re.S)
    if not m:
        raise ValueError("Hipcamp page had no __NEXT_DATA__ (blocked, or the page changed)")
    props = json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    place = (props.get("query") or {}).get("place")
    if not place:  # e.g. small towns get a different page layout with no listing data
        return []
    lands = []
    for n in (place.get("discoverHipcampLands") or {}).get("nodes") or []:
        coord = n.get("coordinate") or {}
        if n.get("isExternal") or coord.get("latitude") is None:
            continue
        lands.append(Land(
            name=n.get("name", ""),
            lat=coord["latitude"], lon=coord["longitude"],
            path=n.get("url", ""),
            city=n.get("cityName") or "",
            category=n.get("landCategory") or "",
            accommodations=n.get("allAccommodationKeys") or [],
            features=[f.get("slug") for f in n.get("campFeatures") or []],
            price=(n.get("minPricePerNight") or {}).get("format", ""),
            recommends_pct=n.get("recommendsPercentage") if n.get("hasEnoughRecommends") else None,
            recommends_count=n.get("recommendsCount") or 0,
            sites=n.get("totalCampsitesCount"),
        ))
    return lands


def lands_near(places, fetch=None, pause=None):
    """Hipcamp listings from the town pages for each place, de-duplicated."""
    fetch = fetch or web.fetch_text
    found, errors = {}, []
    for place in places:
        url = town_page(place)
        if not url:
            continue
        try:
            for land in parse_town_page(fetch(url)):
                found.setdefault(land.path, land)
        except Exception as e:
            errors.append(f"Hipcamp ({place}): {e}")
        if pause:
            pause()
    return list(found.values()), errors
