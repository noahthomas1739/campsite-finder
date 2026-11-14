"""Command-line entry point.

Examples:
    python -m campsite_finder --from "Columbus, OH" --drive-hours 2 --direction east --electric
    python -m campsite_finder --route "San Antonio, TX" "Austin, TX" "Waco, TX" "Dallas, TX" --electric
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import campspot, geo, hipcamp, recgov, texas


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="campsite-finder",
        description=("Find available campsites (Recreation.gov and Texas State Parks) within a few "
                     "hours' drive of you, in the direction you want to head."),
    )
    where = p.add_argument_group("where")
    where.add_argument("--from", dest="origin", help='Where you are starting, e.g. "Denver, CO" or a zip code')
    where.add_argument("--lat", type=float, help="Starting latitude (instead of --from)")
    where.add_argument("--lon", type=float, help="Starting longitude (instead of --from)")
    where.add_argument("--drive-hours", type=float, default=2.0,
                       help="Furthest you're willing to drive; anything closer counts too (default: 2)")
    where.add_argument("--mph", type=float, default=55.0,
                       help="Straight-line miles covered per hour of driving (default: 55)")
    where.add_argument("--direction", default="east",
                       help="Only places in this direction from you: north, ne, east, se, ... or 'any' (default: east)")
    where.add_argument("--spread", type=float, default=60.0,
                       help="Degrees either side of --direction to include; 60 means NE through SE for east (default: 60)")
    where.add_argument("--route", nargs="+", action="append", metavar="PLACE",
                       help="Search along a drive instead of around --from: list the towns in order. "
                            "Repeat --route to compare alternative routes")
    where.add_argument("--detour-hours", type=float, default=1.0,
                       help="With --route: furthest off the route you'll go (default: 1)")

    when = p.add_argument_group("when")
    when.add_argument("--start", type=date.fromisoformat, help="Check-in date YYYY-MM-DD (default: this Friday)")
    when.add_argument("--nights", type=int, help="Number of nights (default: through Sunday)")

    what = p.add_argument_group("what")
    what.add_argument("--electric", action="store_true", help="Only sites with an electric hookup")
    what.add_argument("--all-site-types", action="store_true",
                      help="Include horse, group, pavilion, picnic, shelter and cabin sites (hidden by default)")
    what.add_argument("--max-campgrounds", type=int, default=80,
                      help="Max Recreation.gov campgrounds to check, nearest first (default: 80)")
    what.add_argument("--show-sites", type=int, default=5, help="Sites to list per campground (default: 5)")
    what.add_argument("--no-state-parks", action="store_true",
                      help="Skip checking Texas State Parks")
    what.add_argument("--no-private", action="store_true",
                      help="Skip private campgrounds (Campspot and Hipcamp)")
    what.add_argument("--workers", type=int, default=4, help="Parallel requests (be polite; default: 4)")
    args = p.parse_args(argv)

    if not args.route and args.origin is None and (args.lat is None or args.lon is None):
        p.error("give --from \"City, ST\", both --lat and --lon, or --route")
    if args.route and any(len(r) < 2 for r in args.route):
        p.error("each --route needs at least two places")
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

    stay = f"{check_in:%a %b %d} -> {check_out:%a %b %d}{' (electric hookups only)' if args.electric else ''}"
    if args.route:
        in_range, place, nearby = route_area(args, stay)
    else:
        in_range, place, nearby = radius_area(args, stay)

    campgrounds = [cg for cg in nearby if in_range(cg.lat, cg.lon)]
    campgrounds.sort(key=lambda cg: place(cg.lat, cg.lon)[0])
    campgrounds = campgrounds[:args.max_campgrounds]
    print(f"Checking {len(campgrounds)} Recreation.gov campgrounds ...", file=sys.stderr)

    def check(cg):
        result = recgov.CampgroundResult(cg, *place(cg.lat, cg.lon))
        try:
            result.sites = recgov.available_sites(cg.id, check_in, check_out, electric_only=args.electric,
                                                 standard_only=not args.all_site_types)
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
        parks = [p for p in texas.PARKS if in_range(p.lat, p.lon)]
        if parks:
            print(f"Checking {len(parks)} Texas State Parks ...", file=sys.stderr)

        def check_park(park):
            result = texas.StateParkResult(park, *place(park.lat, park.lon))
            try:
                result.sites = texas.available_sites(park, check_in, check_out, electric_only=args.electric,
                                                    standard_only=not args.all_site_types)
            except Exception as e:
                result.error = str(e)
            return result

        # Kept to 2 at a time: these are full web pages, not a lightweight API.
        with ThreadPoolExecutor(max_workers=2) as pool:
            park_results = list(pool.map(check_park, parks))
        park_hits = sorted((r for r in park_results if r.sites), key=lambda r: r.distance_mi)
        errors += [f"{r.park.name}: {r.error}" for r in park_results if r.error]
        print_state_parks(park_hits, check_in, check_out, args.show_sites, checked=len(parks))

    cs_hits = []
    if not args.no_private:
        towns = [n for r in args.route for n in r] if args.route else [args.origin] if args.origin else []
        towns = list(dict.fromkeys(towns))
        if towns:
            print(f"Checking private campgrounds on Campspot near {len(towns)} town(s) ...", file=sys.stderr)
            cs_parks, cs_errors = campspot.parks_near(towns)
            errors += cs_errors
            cs_parks = [p for p in cs_parks if in_range(p.lat, p.lon)]
            cs_results = []
            for p in cs_parks:
                r = campspot.ParkResult(p, *place(p.lat, p.lon))
                try:
                    r.sites = campspot.available_sites(p, check_in, check_out, electric_only=args.electric,
                                                       standard_only=not args.all_site_types)
                except Exception as e:
                    errors.append(f"{p.name} (Campspot): {e}")
                cs_results.append(r)
            cs_hits = sorted((r for r in cs_results if r.sites), key=lambda r: r.distance_mi)
            print_campspot(cs_hits, check_in, check_out, checked=len(cs_parks))

            print(f"Looking up private campgrounds on Hipcamp near {len(towns)} town(s) ...", file=sys.stderr)
            lands, land_errors = hipcamp.lands_near(towns, pause=lambda: time.sleep(2))
            errors += land_errors
            land_hits = sorted(
                (hipcamp.LandResult(l, *place(l.lat, l.lon)) for l in lands
                 if in_range(l.lat, l.lon)
                 and (l.electric or not args.electric)
                 and (args.all_site_types or not l.lodging_only)),
                key=lambda r: r.distance_mi)
            print_private(land_hits, check_in, check_out, args.electric)

    if errors:
        print(f"\n{len(errors)} place(s) could not be checked:", file=sys.stderr)
        for e in errors[:8]:
            print(f"  - {e}"[:200], file=sys.stderr)
    return 0 if hits or park_hits or cs_hits else 1


def radius_area(args, stay):
    """Everything within drive-hours of one starting point, optionally in one direction."""
    if args.origin:
        print(f"Locating {args.origin} ...", file=sys.stderr)
        o_lat, o_lon = geo.geocode(args.origin)
    else:
        o_lat, o_lon = args.lat, args.lon
    radius = args.drive_hours * args.mph
    direction = args.direction.lower()

    def in_range(lat, lon):
        if geo.haversine_mi(o_lat, o_lon, lat, lon) > radius:
            return False
        if direction == "any":
            return True
        return geo.within_heading(geo.bearing_deg(o_lat, o_lon, lat, lon), geo.DIRECTIONS[direction], args.spread)

    def place(lat, lon):
        return geo.haversine_mi(o_lat, o_lon, lat, lon), None

    print(f"Searching up to {radius:.0f} mi (straight-line) {'in every direction' if direction == 'any' else direction} "
          f"of you for {stay} ...", file=sys.stderr)
    return in_range, place, recgov.search_campgrounds(o_lat, o_lon, radius, limit=500)


def route_area(args, stay):
    """Everything within detour-hours of any of the routes, ordered by how far along the trip it is."""
    coords = {}
    for name in dict.fromkeys(n for r in args.route for n in r):
        print(f"Locating {name} ...", file=sys.stderr)
        coords[name] = geo.geocode(name)
        time.sleep(1)  # Nominatim's usage policy: at most one request a second
    routes = [[coords[n] for n in r] for r in args.route]
    detour = args.detour_hours * args.mph

    def place(lat, lon):
        # (miles along the trip, miles off the road) for whichever route passes closest
        off, along = min(geo.route_position(lat, lon, r) for r in routes)
        return along, off

    def in_range(lat, lon):
        return place(lat, lon)[1] <= detour

    print(f"Searching within {detour:.0f} mi (straight-line) of "
          + " or ".join(" -> ".join(r) for r in args.route) + f" for {stay} ...", file=sys.stderr)
    found = {}
    for r in routes:
        for lat, lon in geo.points_along(r, 60):
            for cg in recgov.search_campgrounds(lat, lon, detour + 40, limit=500):
                found.setdefault(cg.id, cg)
    return in_range, place, list(found.values())


def where(r):
    if r.off_route_mi is None:
        return f"{r.distance_mi:.0f} mi straight-line"
    return f"{r.distance_mi:.0f} mi along the route, {r.off_route_mi:.0f} mi off it"


def print_results(hits, check_in, check_out, show_sites):
    if not hits:
        print("\nRecreation.gov: no campgrounds with a site open for every night of that stay.\n")
        return
    nights = (check_out - check_in).days
    print(f"\n{len(hits)} campground(s) with sites open all {nights} night(s):\n")
    for r in hits:
        cg = r.campground
        loc = ", ".join(x for x in (cg.city.title(), cg.state) if x)
        print(f"{cg.name}  ({where(r)}{'; ' + loc if loc else ''})")
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
        print(f"{p.name}  ({where(r)})")
        print(f"  {len(r.sites)} site(s) open  ->  {p.url(check_in, nights)}")
        for s in r.sites[:show_sites]:
            loop = f"{s.loop} " if s.loop else ""
            amps = f", {s.electric_amps} amp" if s.electric_amps else ""
            rate = f"  {s.rate}/night" if s.rate else ""
            print(f"    - {loop}site {s.name}: {s.site_type}{amps}{rate}")
        if len(r.sites) > show_sites:
            print(f"    ... and {len(r.sites) - show_sites} more")
        print()


def print_campspot(hits, check_in, check_out, checked):
    if not checked:
        return
    if not hits:
        print(f"Campspot: none of the {checked} private campground(s) in range have a site open for every night.\n")
        return
    nights = (check_out - check_in).days
    print(f"{len(hits)} private campground(s) on Campspot with sites open all {nights} night(s):\n")
    for r in hits:
        p = r.park
        print(f"{p.name}  ({where(r)})")
        print(f"  {sum(s.open_count for s in r.sites)} site(s) open  ->  {p.url(check_in, check_out)}")
        for s in r.sites:
            price = f"  ${s.price_per_night:.0f}/night" if s.price_per_night else ""
            amps = f", {s.amps} amp" if s.amps else ""
            print(f"    - {s.name} ({s.category}{amps}): {s.open_count} open{price}")
        print()


def print_private(hits, check_in, check_out, electric):
    if not hits:
        print("Hipcamp: no private campgrounds found in range.\n")
        return
    print(f"{len(hits)} private campground(s) on Hipcamp{' with electric hookups' if electric else ''}. "
          f"Availability isn't checked; the link opens your dates:\n")
    for r in hits:
        l = r.land
        rating = f"{l.recommends_pct}% recommend ({l.recommends_count})" if l.recommends_pct is not None else "new"
        kinds = "/".join(k for k in l.accommodations if k in ("tent", "rv", "house")).replace("house", "lodging")
        print(f"{l.name}  ({where(r)}{'; ' + l.city if l.city else ''})")
        print(f"  {rating} · from {l.price or '?'}/night · {kinds}  ->  {l.url(check_in, check_out)}")
    print()


if __name__ == "__main__":
    sys.exit(main())
