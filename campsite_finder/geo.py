"""Geocoding and simple great-circle math."""

import json
import math
import urllib.parse
import urllib.request

EARTH_RADIUS_MI = 3958.8
USER_AGENT = "campsite-finder/0.1 (personal campsite availability search)"

DIRECTIONS = {
    "north": 0, "n": 0,
    "northeast": 45, "ne": 45,
    "east": 90, "e": 90,
    "southeast": 135, "se": 135,
    "south": 180, "s": 180,
    "southwest": 225, "sw": 225,
    "west": 270, "w": 270,
    "northwest": 315, "nw": 315,
}


def geocode(place):
    """Turn an address/city/zip into (lat, lon) using OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": place, "format": "json", "limit": 1, "countrycodes": "us"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:
        results = json.load(resp)
    if not results:
        raise ValueError(f"Could not find a location for {place!r}")
    return float(results[0]["lat"]), float(results[0]["lon"])


def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Compass bearing (0 = north, 90 = east) from point 1 to point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def within_heading(bearing, heading, spread):
    """True if bearing is within +/- spread degrees of heading."""
    return abs((bearing - heading + 180) % 360 - 180) <= spread


def _plane(lat, lon, lat0):
    """Local flat-earth miles; fine for the few hundred miles of a driving route."""
    return lon * 69.17 * math.cos(math.radians(lat0)), lat * 69.0


def route_position(lat, lon, route):
    """(miles off the route, miles along it from the start to the nearest point) for a
    point and a route given as [(lat, lon), ...] waypoints joined by straight lines."""
    px, py = _plane(lat, lon, lat)
    best_off, best_along, travelled = None, 0.0, 0.0
    for (alat, alon), (blat, blon) in zip(route, route[1:]):
        ax, ay = _plane(alat, alon, lat)
        bx, by = _plane(blat, blon, lat)
        dx, dy = bx - ax, by - ay
        seg = math.hypot(dx, dy)
        t = 0.0 if seg == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg ** 2))
        off = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if best_off is None or off < best_off:
            best_off, best_along = off, travelled + t * seg
        travelled += seg
    return best_off, best_along


def points_along(route, every_mi):
    """Waypoints plus extra points so no two consecutive points are more than every_mi apart."""
    pts = [route[0]]
    for (alat, alon), (blat, blon) in zip(route, route[1:]):
        steps = max(1, math.ceil(haversine_mi(alat, alon, blat, blon) / every_mi))
        for i in range(1, steps + 1):
            pts.append((alat + (blat - alat) * i / steps, alon + (blon - alon) * i / steps))
    return pts
