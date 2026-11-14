"""Private campgrounds that book through Campspot.

- Area pages (/c/camping-in-<state>/near-<town>) list nearby parks; each park's name,
  coordinates and page are in schema.org "Campground" JSON inside the page's streamed
  Next.js data (self.__next_f.push chunks), and its starting price is on the park card.
- Park pages (/park/<slug>) carry the numeric park id in their component props.
- Availability is the same request the park page makes in the browser:
  GET /api/gator-core/v2/availability/parks/<id>?adults=..&checkin=..&checkout=..&includeUnavailable=true
  with header x-client-type: AGGREGATOR. It returns a list of site types, each with an
  availability status, prices, amenities and its individual campsites.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
from dataclasses import dataclass, field

from . import web
from .filters import is_specialty

BASE = "https://www.campspot.com"
API = BASE + "/api/gator-core/v2"
API_HEADERS = dict(web.HEADERS, **{"Accept": "application/json", "x-client-type": "AGGREGATOR"})
STATES = {"TX": "texas", "OK": "oklahoma", "LA": "louisiana", "NM": "new-mexico", "AR": "arkansas"}


@dataclass
class Park:
    name: str
    slug: str
    lat: float
    lon: float
    starting_price: str = ""

    def url(self, check_in=None, check_out=None, adults=2):
        if not check_in:
            return f"{BASE}/park/{self.slug}"
        return f"{BASE}/park/{self.slug}?" + urllib.parse.urlencode({
            "checkin": check_in.isoformat(), "checkout": check_out.isoformat(),
            "adults": adults, "children": 0, "pets": 0})


@dataclass
class SiteType:
    name: str
    category: str  # tent / rv / lodging
    open_count: int
    electric: bool
    price_per_night: float | None = None
    amps: str = ""


@dataclass
class ParkResult:
    park: Park
    distance_mi: float
    off_route_mi: float | None = None
    sites: list = field(default_factory=list)
    error: str | None = None


def area_page(place):
    """'Canyon Lake, TX' -> Campspot area page URL, or None if the state isn't mapped."""
    town, _, state = (p.strip() for p in place.rpartition(","))
    state = STATES.get(state.upper())
    if not (town and state):
        return None
    slug = re.sub(r"[^a-z0-9]+", "-", town.lower()).strip("-")
    return f"{BASE}/c/camping-in-{state}/near-{slug}"


def parse_area_page(page_html):
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', page_html, re.S)
    if not chunks:
        raise ValueError("Campspot area page had no park data (blocked, or the page changed)")
    text = "".join(json.loads('"' + c + '"') for c in chunks)
    prices = dict(re.findall(
        r'"href":"https://www\.campspot\.com/park/([A-Za-z0-9_-]+)"[^{}]*?"cs-starting-at":"\$\$([0-9.]+)"', text))
    parks = []
    for m in re.finditer(r'"__html":"(\{\\"@context\\":\\"https://schema.org\\",\\"@type\\":\\"Campground\\".*?)(?<!\\)"\}',
                         text):
        data = json.loads(json.loads('"' + m.group(1) + '"'))
        geo = data.get("geo") or {}
        slug = (data.get("mainEntityOfPage") or "").rstrip("/").rsplit("/park/", 1)[-1]
        if not slug or geo.get("latitude") is None:
            continue
        price = prices.get(slug)
        parks.append(Park(name=data.get("name", ""), slug=slug, lat=float(geo["latitude"]),
                          lon=float(geo["longitude"]), starting_price=f"${float(price):.0f}" if price else ""))
    return parks


def parse_park_id(page_html):
    m = re.search(r'"parkId":\[0,(\d+)\]', html.unescape(page_html))
    if not m:
        raise ValueError("Campspot park page had no park id (blocked, or the page changed)")
    return int(m.group(1))


def is_electric(amenities):
    return any(a == "Electricity" or re.fullmatch(r"\d+-Amp", a) for a in amenities or [])


def parse_availability(site_types, electric_only=False, standard_only=True):
    """Site types with at least one campsite open for the whole stay."""
    if not isinstance(site_types, list):
        raise ValueError("Campspot availability response was not a list")
    out = []
    for t in site_types:
        category = t.get("campsiteCategoryCode") or ""
        amenities = t.get("amenities") or []
        if standard_only and (category == "lodging" or is_specialty(t.get("name"))):
            continue
        if electric_only and not is_electric(amenities):
            continue
        campsites = t.get("campsites")
        if campsites:
            open_count = sum(1 for c in campsites if c.get("availability") == "AVAILABLE")
        else:
            open_count = 1 if t.get("availability") == "AVAILABLE" else 0
        if not open_count:
            continue
        amps = sorted({a.split("-")[0] for a in amenities if re.fullmatch(r"\d+-Amp", a)}, key=int)
        out.append(SiteType(
            name=t.get("name", ""), category=category, open_count=open_count,
            electric=is_electric(amenities),
            price_per_night=t.get("averagePricePerNight") or t.get("lowestBaselinePrice"),
            amps="/".join(amps),
        ))
    return out


def availability_url(park_id, check_in, check_out, adults=2):
    return f"{API}/availability/parks/{park_id}?" + urllib.parse.urlencode({
        "adults": adults, "children": 0, "pets": 0, "includeUnavailable": "true",
        "checkin": check_in.isoformat(), "checkout": check_out.isoformat()})


def parks_near(places, fetch=None, pause=1.0):
    """Campspot parks listed on the area page for each place, de-duplicated."""
    fetch = fetch or web.fetch_text
    found, errors = {}, []
    for place in places:
        url = area_page(place)
        if not url:
            continue
        try:
            for park in parse_area_page(fetch(url)):
                found.setdefault(park.slug, park)
        except Exception as e:
            errors.append(f"Campspot ({place}): {e}")
        time.sleep(pause)
    return list(found.values()), errors


def available_sites(park, check_in, check_out, electric_only=False, standard_only=True, fetch=None, pause=1.0):
    fetch = fetch or web.fetch_text
    park_id = parse_park_id(fetch(park.url()))
    time.sleep(pause)
    data = json.loads(fetch(availability_url(park_id, check_in, check_out), headers=API_HEADERS))
    return parse_availability(data, electric_only, standard_only)
