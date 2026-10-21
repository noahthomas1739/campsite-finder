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


def destination_point(lat, lon, bearing_deg, distance_mi):
    """Point reached by travelling distance_mi from (lat, lon) along bearing_deg."""
    d = distance_mi / EARTH_RADIUS_MI
    b = math.radians(bearing_deg)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(p1),
        math.cos(d) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def haversine_mi(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))
