"""Texas State Parks (booked through texasstateparks.reserveamerica.com).

ReserveAmerica has no public availability API, so this provider doesn't check
open sites. It lists the parks inside your search area with a direct booking
link, so you open a few known pages instead of hunting for them.

Park IDs come from the parkId= parameter on each park's ReserveAmerica page.
Coordinates are approximate park locations, used only for distance filtering.
"""

from dataclasses import dataclass

BASE = "https://texasstateparks.reserveamerica.com"


@dataclass
class StatePark:
    name: str
    slug: str
    park_id: int
    lat: float
    lon: float
    electric: bool = True
    notes: str = ""

    @property
    def url(self):
        return f"{BASE}/camping/{self.slug}/r/campgroundDetails.do?contractCode=TX&parkId={self.park_id}"


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


def parks_near(lat, lon, radius_mi, distance_fn, electric_only=False):
    """Parks within radius_mi of (lat, lon), nearest first."""
    hits = []
    for p in PARKS:
        if electric_only and not p.electric:
            continue
        d = distance_fn(lat, lon, p.lat, p.lon)
        if d <= radius_mi:
            hits.append((d, p))
    return [p for _, p in sorted(hits, key=lambda x: x[0])]
