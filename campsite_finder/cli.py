"""Command-line entry point.

Example:
    python -m campsite_finder --from "Columbus, OH" --drive-hours 2 --direction east --electric
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import geo, recgov, texas


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="campsite-finder",
        description="Find available campsites on Recreation.gov around a point a few hours' drive away.",
    )
    where = p.add_argument_group("where")
    where.add_argument("--from", dest="origin", help='Where you are starting, e.g. "Denver, CO" or a zip code')
    where.add_argument("--lat", type=float, help="Starting latitude (instead of --from)")
    where.add_argument("--lon", type=float, help="Starting longitude (instead of --from)")
    where.add_argument("--drive-hours", type=float, default=2.0, help="How far you want to drive (default: 2)")
    where.add_argument("--mph", type=float, default=50.0,
                       help="Average straight-line progress per hour, used to turn hours into miles (default: 50)")
    where.add_argument("--direction", default="east",
                       help="Compass direction to head: north, ne, east, se, ... or 'any' to search around you (default: east)")
    where.add_argument("--radius", type=float, default=40.0,
                       help="Search radius in miles around the target point (default: 40)")

    when = p.add_argument_group("when")
    when.add_argument("--start", type=date.fromisoformat, help="Check-in date YYYY-MM-DD (default: this Friday)")
    when.add_argument("--nights", type=int, help="Number of nights (default: through Sunday)")

    what = p.add_argument_group("what")
    what.add_argument("--electric", action="store_true", help="Only sites with an electric hookup")
    what.add_argument("--max-campgrounds", type=int, default=60, help="Max campgrounds to check (default: 60)")
    what.add_argument("--show-sites", type=int, default=5, help="Sites to list per campground (default: 5)")
    what.add_argument("--no-state-parks", action="store_true",
                      help="Skip checking Texas State Parks")
    what.add_argument("--workers", type=int, default=4, help="Parallel requests (be polite; default: 4)")
    args = p.parse_args(argv)

    if args.origin is None and (args.lat is None or args.lon is None):
        p.error("give --from \"City, ST\" or both --lat and --lon")
    if args.direction.lower() != "any" and args.direction.lower() not in geo.DIRECTIONS:
        p.error(f"unknown direction {args.direction!r}")
    return args


def resolve_dates(args, today=None):
    if args.start:
        check_in = args.start
        check_out = check_in + timedelta(days=args.nights or 2)
    else:
        check_in, check_out = recgov.upcoming_weekend(today)
        if args.nights:
            check_out = check_in + timedelta(days=args.nights)
    return check_in, check_out


def main(argv=None):
    args = parse_args(argv)
    check_in, check_out = resolve_dates(args)

    if args.origin:
        print(f"Locating {args.origin} ...", file=sys.stderr)
        o_lat, o_lon = geo.geocode(args.origin)
    else:
        o_lat, o_lon = args.lat, args.lon

    if args.direction.lower() == "any":
        c_lat, c_lon = o_lat, o_lon
        radius = max(args.radius, args.drive_hours * args.mph)
    else:
        dist = args.drive_hours * args.mph
        c_lat, c_lon = geo.destination_point(o_lat, o_lon, geo.DIRECTIONS[args.direction.lower()], dist)
        radius = args.radius

    print(f"Searching within {radius:.0f} mi of ({c_lat:.3f}, {c_lon:.3f}) "
          f"for {check_in:%a %b %d} -> {check_out:%a %b %d}"
          f"{' (electric hookups only)' if args.electric else ''} ...", file=sys.stderr)

    campgrounds = recgov.search_campgrounds(c_lat, c_lon, radius, limit=args.max_campgrounds)
    print(f"Checking {len(campgrounds)} campgrounds ...", file=sys.stderr)

    def check(cg):
        result = recgov.CampgroundResult(cg, geo.haversine_mi(o_lat, o_lon, cg.lat, cg.lon))
        try:
            result.sites = recgov.available_sites(cg.id, check_in, check_out, electric_only=args.electric)
        except Exception as e:  # one bad campground shouldn't sink the whole search
            result.error = str(e)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(check, campgrounds))

    hits = sorted((r for r in results if r.sites), key=lambda r: r.distance_mi)
    errors = [f"{r.campground.name}: {r.error}" for r in results if r.error]
    print_results(hits, check_in, check_out, args.show_sites)

    park_hits = []
    if not args.no_state_parks:
        parks = texas.parks_near(c_lat, c_lon, radius, geo.haversine_mi)
        if parks:
            print(f"Checking {len(parks)} Texas State Parks ...", file=sys.stderr)

        def check_park(park):
            result = texas.StateParkResult(park, geo.haversine_mi(o_lat, o_lon, park.lat, park.lon))
            try:
                result.sites = texas.available_sites(park, check_in, check_out, electric_only=args.electric)
            except Exception as e:
                result.error = str(e)
            return result

        # Kept to 2 at a time: these are full web pages, not a lightweight API.
        with ThreadPoolExecutor(max_workers=2) as pool:
            park_results = list(pool.map(check_park, parks))
        park_hits = sorted((r for r in park_results if r.sites), key=lambda r: r.distance_mi)
        errors += [f"{r.park.name}: {r.error}" for r in park_results if r.error]
        print_state_parks(park_hits, check_in, check_out, args.show_sites, checked=len(parks))

    if errors:
        print(f"\n{len(errors)} place(s) could not be checked:", file=sys.stderr)
        for e in errors[:8]:
            print(f"  - {e}"[:200], file=sys.stderr)
    return 0 if hits or park_hits else 1


def print_results(hits, check_in, check_out, show_sites):
    if not hits:
        print("\nRecreation.gov: no campgrounds with a site open for every night of that stay.\n")
        return
    nights = (check_out - check_in).days
    print(f"\n{len(hits)} campground(s) with sites open all {nights} night(s):\n")
    for r in hits:
        cg = r.campground
        loc = ", ".join(x for x in (cg.city.title(), cg.state) if x)
        print(f"{cg.name}  ({r.distance_mi:.0f} mi straight-line{'; ' + loc if loc else ''})")
        print(f"  {len(r.sites)} site(s) open  ->  {cg.url}")
        for s in r.sites[:show_sites]:
            loop = f"{s.loop} " if s.loop else ""
            print(f"    - {loop}site {s.name}: {s.campsite_type.title()}  {s.url}")
        if len(r.sites) > show_sites:
            print(f"    ... and {len(r.sites) - show_sites} more")
        print()


def print_state_parks(hits, check_in, check_out, show_sites, checked):
    if not checked:
        return
    if not hits:
        print(f"Texas State Parks: none of the {checked} park(s) in range have a site open for every night.\n")
        return
    nights = (check_out - check_in).days
    print(f"{len(hits)} Texas State Park(s) with sites open all {nights} night(s):\n")
    for r in hits:
        p = r.park
        print(f"{p.name}  ({r.distance_mi:.0f} mi straight-line)")
        print(f"  {len(r.sites)} site(s) open  ->  {p.url(check_in, nights)}")
        for s in r.sites[:show_sites]:
            loop = f"{s.loop} " if s.loop else ""
            amps = f", {s.electric_amps} amp" if s.electric_amps else ""
            rate = f"  {s.rate}/night" if s.rate else ""
            print(f"    - {loop}site {s.name}: {s.site_type}{amps}{rate}")
        if len(r.sites) > show_sites:
            print(f"    ... and {len(r.sites) - show_sites} more")
        print()

if __name__ == "__main__":
    sys.exit(main())
