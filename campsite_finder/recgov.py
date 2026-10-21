"""Recreation.gov provider.

Uses the same JSON endpoints the recreation.gov website calls:
  - /api/search                                  find campgrounds near a point
  - /api/camps/availability/campground/{id}/month  per-site, per-night availability
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, timedelta

BASE = "https://www.recreation.gov"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (campsite-finder personal availability checker)",
    "Accept": "application/json",
}


@dataclass
class Campground:
    id: str
    name: str
    lat: float
    lon: float
    city: str = ""
    state: str = ""

    @property
    def url(self):
        return f"{BASE}/camping/campgrounds/{self.id}"


@dataclass
class Site:
    id: str
    name: str
    loop: str
    campsite_type: str
    type_of_use: str
    max_people: int | None = None

    @property
    def url(self):
        return f"{BASE}/camping/campsites/{self.id}"


@dataclass
class CampgroundResult:
    campground: Campground
    distance_mi: float
    sites: list = field(default_factory=list)
    error: str | None = None


def _get_json(path, params=None, retries=3):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            # 429 / 5xx are worth retrying; anything else is a real error.
            if e.code != 429 and e.code < 500 or attempt == retries - 1:
                raise
        except urllib.error.URLError:
            if attempt == retries - 1:
                raise
        time.sleep(2 ** attempt)


def search_campgrounds(lat, lon, radius_mi, limit=100):
    """Reservable campgrounds within radius_mi of (lat, lon)."""
    found, start = [], 0
    while len(found) < limit:
        data = _get_json("/api/search", {
            "fq": "entity_type:campground",
            "lat": lat,
            "lng": lon,
            "radius": radius_mi,
            "size": 50,
            "start": start,
        })
        results = data.get("results") or []
        for r in results:
            if r.get("reservable") is False:
                continue
            try:
                cg_lat, cg_lon = float(r["latitude"]), float(r["longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            found.append(Campground(
                id=str(r["entity_id"]),
                name=r.get("name", "").title(),
                lat=cg_lat,
                lon=cg_lon,
                city=r.get("city", "") or "",
                state=r.get("state_code", "") or "",
            ))
        start += len(results)
        if not results or start >= data.get("total", 0):
            break
    return found[:limit]


def is_electric(campsite_type):
    """recreation.gov encodes hookups in the site type, e.g. 'STANDARD ELECTRIC'
    vs 'STANDARD NONELECTRIC' (note the substring trap)."""
    t = (campsite_type or "").upper().replace("-", "")
    return "ELECTRIC" in t and "NONELECTRIC" not in t


def _months(start, end):
    """First-of-month dates covering nights start..end-1."""
    m = start.replace(day=1)
    last = (end - timedelta(days=1)).replace(day=1)
    while m <= last:
        yield m
        m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)


def available_sites(campground_id, check_in, check_out, electric_only=False, type_of_use="Overnight"):
    """Sites that are 'Available' for every night from check_in up to check_out."""
    nights = [check_in + timedelta(days=i) for i in range((check_out - check_in).days)]
    merged = {}
    for month in _months(check_in, check_out):
        data = _get_json(
            f"/api/camps/availability/campground/{campground_id}/month",
            {"start_date": month.strftime("%Y-%m-01T00:00:00.000Z")},
        )
        for sid, site in (data.get("campsites") or {}).items():
            entry = merged.setdefault(sid, dict(site, availabilities={}))
            entry["availabilities"].update(site.get("availabilities") or {})

    sites = []
    for sid, s in merged.items():
        if type_of_use and s.get("type_of_use") not in (None, type_of_use):
            continue
        if electric_only and not is_electric(s.get("campsite_type")):
            continue
        avail = s["availabilities"]
        if all(avail.get(n.strftime("%Y-%m-%dT00:00:00Z")) == "Available" for n in nights):
            sites.append(Site(
                id=str(s.get("campsite_id", sid)),
                name=str(s.get("site", "")),
                loop=s.get("loop", "") or "",
                campsite_type=s.get("campsite_type", "") or "",
                type_of_use=s.get("type_of_use", "") or "",
                max_people=s.get("max_num_people"),
            ))
    sites.sort(key=lambda x: (x.loop, x.name))
    return sites


def upcoming_weekend(today=None):
    """Friday check-in / Sunday check-out for this weekend (or next, if it's already Sunday)."""
    today = today or date.today()
    sunday = today + timedelta(days=(6 - today.weekday()) % 7 or 7)
    if today.weekday() == 5:  # Saturday: just tonight
        return today, sunday
    return sunday - timedelta(days=2), sunday
