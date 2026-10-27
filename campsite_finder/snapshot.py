"""Write a JSON snapshot of open sites (every night for the next two weeks) for the web page.

    python -m campsite_finder.snapshot --lat 32.9343 --lon -97.0781 --direction any --out site/data.json

The page (site/index.html) works out which sites are open for a chosen stay from
each site's list of open nights, so one snapshot answers every stay in the window.
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

from . import geo, recgov, texas

COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def compass(bearing):
    return COMPASS[int((bearing + 22.5) // 45) % 8]


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="campsite_finder.snapshot")
    p.add_argument("--lat", type=float, required=True)
    p.add_argument("--lon", type=float, required=True)
    p.add_argument("--origin-name", default="", help="Shown on the page, e.g. Grapevine, TX")
    p.add_argument("--drive-hours", type=float, default=2.0)
    p.add_argument("--mph", type=float, default=55.0)
    p.add_argument("--direction", default="any")
    p.add_argument("--spread", type=float, default=60.0)
    p.add_argument("--days", type=int, default=14, help="Nights to cover, starting today (max 14)")
    p.add_argument("--max-campgrounds", type=int, default=120)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def build(args, today=None):
    today = today or date.today()
    days = min(args.days, 14)  # ReserveAmerica's availability grid covers 14 nights
    end = today + timedelta(days=days)
    radius = args.drive_hours * args.mph
    direction = args.direction.lower()

    def place(lat, lon):
        d = geo.haversine_mi(args.lat, args.lon, lat, lon)
        b = geo.bearing_deg(args.lat, args.lon, lat, lon)
        ok = d <= radius and (direction == "any" or
                              geo.within_heading(b, geo.DIRECTIONS[direction], args.spread))
        return ok, round(d, 1), compass(b)

    campgrounds, errors = [], []

    nearby = []
    for cg in recgov.search_campgrounds(args.lat, args.lon, radius, limit=500):
        ok, d, heading = place(cg.lat, cg.lon)
        if ok:
            nearby.append((d, heading, cg))
    nearby = sorted(nearby, key=lambda x: x[0])[:args.max_campgrounds]

    def check_cg(item):
        d, heading, cg = item
        try:
            sites = recgov.site_nights(cg.id, today, end)
        except Exception as e:
            return None, f"{cg.name}: {e}"
        return {
            "name": cg.name, "source": "Recreation.gov", "miles": d, "heading": heading, "url": cg.url,
            "sites": [{
                "name": s.name, "loop": s.loop.strip(), "type": s.campsite_type.title(),
                "electric": recgov.is_electric(s.campsite_type), "amps": "", "rate": "",
                "url": s.url, "open": nights,
            } for s, nights in sites],
        }, None

    def check_park(item):
        d, heading, park = item
        try:
            sites = texas.site_nights(park, today, days)
        except Exception as e:
            return None, f"{park.name}: {e}"
        return {
            "name": park.name, "source": "Texas State Parks", "miles": d, "heading": heading,
            "url": park.url(), "booking_url_template": park.url() + "?arrivalDate={arrival}&lengthOfStay={nights}",
            "sites": [{
                "name": s.name, "loop": s.loop, "type": s.site_type, "electric": electric,
                "amps": s.electric_amps, "rate": s.rate, "url": "", "open": nights,
            } for s, electric, nights in sites],
        }, None

    parks = []
    for park in texas.PARKS:
        ok, d, heading = place(park.lat, park.lon)
        if ok:
            parks.append((d, heading, park))

    with ThreadPoolExecutor(max_workers=4) as pool:
        recgov_results = list(pool.map(check_cg, nearby))
    with ThreadPoolExecutor(max_workers=2) as pool:
        park_results = list(pool.map(check_park, parks))

    for result, err in recgov_results + park_results:
        if err:
            errors.append(err)
        elif result["sites"]:
            campgrounds.append(result)
    campgrounds.sort(key=lambda c: c["miles"])

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
        "origin": {"name": args.origin_name, "lat": args.lat, "lon": args.lon},
        "radius_miles": round(radius),
        "direction": direction,
        "first_night": today.isoformat(),
        "last_night": (end - timedelta(days=1)).isoformat(),
        "checked": {"recreation_gov": len(nearby), "state_parks": len(parks)},
        "campgrounds": campgrounds,
        "errors": errors,
    }


def main(argv=None):
    args = parse_args(argv)
    started = time.time()
    snapshot = build(args)
    with open(args.out, "w") as f:
        json.dump(snapshot, f, separators=(",", ":"))
    print(f"Wrote {args.out}: {len(snapshot['campgrounds'])} campgrounds with open sites, "
          f"{len(snapshot['errors'])} errors, {time.time() - started:.0f}s", file=sys.stderr)
    for e in snapshot["errors"]:
        print(f"  ! {e}"[:200], file=sys.stderr)
    # Fail the job only if nothing could be checked at all (e.g. blocked everywhere).
    total = snapshot["checked"]["recreation_gov"] + snapshot["checked"]["state_parks"]
    return 1 if total and len(snapshot["errors"]) >= total else 0


if __name__ == "__main__":
    sys.exit(main())
