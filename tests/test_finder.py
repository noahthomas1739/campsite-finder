import json
import os
import unittest
from datetime import date
from unittest import mock

from campsite_finder import campspot, cli, geo, hipcamp, recgov, snapshot, texas, web


def availability(pairs):
    return {f"{d}T00:00:00Z": status for d, status in pairs}


OCT = {
    "campsites": {
        "1": {"campsite_id": "1", "site": "A01", "loop": "A", "campsite_type": "STANDARD ELECTRIC",
              "type_of_use": "Overnight",
              "availabilities": availability([("2026-10-23", "Available"), ("2026-10-24", "Available")])},
        "2": {"campsite_id": "2", "site": "A02", "loop": "A", "campsite_type": "STANDARD NONELECTRIC",
              "type_of_use": "Overnight",
              "availabilities": availability([("2026-10-23", "Available"), ("2026-10-24", "Available")])},
        "3": {"campsite_id": "3", "site": "B01", "loop": "B", "campsite_type": "RV ELECTRIC",
              "type_of_use": "Overnight",
              "availabilities": availability([("2026-10-23", "Available"), ("2026-10-24", "Reserved")])},
        "4": {"campsite_id": "4", "site": "C01", "loop": "C", "campsite_type": "STANDARD ELECTRIC",
              "type_of_use": "Day",
              "availabilities": availability([("2026-10-23", "Available"), ("2026-10-24", "Available")])},
    }
}


class ElectricTest(unittest.TestCase):
    def test_types(self):
        self.assertTrue(recgov.is_electric("STANDARD ELECTRIC"))
        self.assertTrue(recgov.is_electric("RV ELECTRIC"))
        self.assertFalse(recgov.is_electric("STANDARD NONELECTRIC"))
        self.assertFalse(recgov.is_electric("STANDARD NON-ELECTRIC"))
        self.assertFalse(recgov.is_electric(None))


class SpecialtyTest(unittest.TestCase):
    def test_recgov_hides_horse_and_group_sites(self):
        data = {"campsites": {
            "1": {"campsite_id": "1", "site": "E01", "campsite_type": "EQUESTRIAN ELECTRIC", "type_of_use": "Overnight",
                  "availabilities": availability([("2026-10-23", "Available")])},
            "2": {"campsite_id": "2", "site": "001", "campsite_type": "GROUP STANDARD ELECTRIC", "type_of_use": "Overnight",
                  "availabilities": availability([("2026-10-23", "Available")])},
            "3": {"campsite_id": "3", "site": "38", "campsite_type": "STANDARD ELECTRIC", "type_of_use": "Overnight",
                  "availabilities": availability([("2026-10-23", "Available")])},
        }}
        with mock.patch.object(recgov, "_get_json", return_value=data):
            default = recgov.available_sites("x", date(2026, 10, 23), date(2026, 10, 24), electric_only=True)
            everything = recgov.available_sites("x", date(2026, 10, 23), date(2026, 10, 24), electric_only=True,
                                                standard_only=False)
        self.assertEqual([s.name for s in default], ["38"])
        self.assertEqual(len(everything), 3)


class AvailabilityTest(unittest.TestCase):
    def test_filters_full_stay_electric_overnight(self):
        with mock.patch.object(recgov, "_get_json", return_value=OCT):
            sites = recgov.available_sites("x", date(2026, 10, 23), date(2026, 10, 25), electric_only=True)
        self.assertEqual([s.name for s in sites], ["A01"])

    def test_without_electric_filter(self):
        with mock.patch.object(recgov, "_get_json", return_value=OCT):
            sites = recgov.available_sites("x", date(2026, 10, 23), date(2026, 10, 25))
        self.assertEqual([s.name for s in sites], ["A01", "A02"])

    def test_stay_spanning_months_fetches_both(self):
        oct_ = {"campsites": {"1": {"campsite_id": "1", "site": "A01", "campsite_type": "STANDARD ELECTRIC",
                                    "type_of_use": "Overnight",
                                    "availabilities": availability([("2026-10-31", "Available")])}}}
        nov = {"campsites": {"1": {"campsite_id": "1", "site": "A01", "campsite_type": "STANDARD ELECTRIC",
                                   "type_of_use": "Overnight",
                                   "availabilities": availability([("2026-11-01", "Available")])}}}
        with mock.patch.object(recgov, "_get_json", side_effect=[oct_, nov]) as m:
            sites = recgov.available_sites("x", date(2026, 10, 31), date(2026, 11, 2))
        self.assertEqual(m.call_count, 2)
        self.assertEqual(len(sites), 1)


class SearchTest(unittest.TestCase):
    def test_skips_unreservable_and_paginates(self):
        page1 = {"total": 3, "results": [
            {"entity_id": "10", "name": "PINE LAKE", "latitude": "40.1", "longitude": "-80.1", "reservable": True},
            {"entity_id": "11", "name": "FIRST COME", "latitude": "40.2", "longitude": "-80.2", "reservable": False},
        ]}
        page2 = {"total": 3, "results": [
            {"entity_id": "12", "name": "OAK HOLLOW", "latitude": "40.3", "longitude": "-80.3"},
        ]}
        with mock.patch.object(recgov, "_get_json", side_effect=[page1, page2]):
            cgs = recgov.search_campgrounds(40, -80, 40)
        self.assertEqual([c.name for c in cgs], ["Pine Lake", "Oak Hollow"])


class DatesTest(unittest.TestCase):
    def test_weekend(self):
        wed = date(2026, 10, 21)
        self.assertEqual(recgov.upcoming_weekend(wed), (date(2026, 10, 23), date(2026, 10, 25)))
        self.assertEqual(recgov.upcoming_weekend(date(2026, 10, 23)), (date(2026, 10, 23), date(2026, 10, 25)))
        self.assertEqual(recgov.upcoming_weekend(date(2026, 10, 24)), (date(2026, 10, 24), date(2026, 10, 25)))
        self.assertEqual(recgov.upcoming_weekend(date(2026, 10, 25)), (date(2026, 10, 30), date(2026, 11, 1)))

    def test_cli_dates(self):
        args = cli.parse_args(["--lat", "40", "--lon", "-80", "--start", "2026-11-06", "--nights", "3"])
        self.assertEqual(cli.resolve_dates(args), (date(2026, 11, 6), date(2026, 11, 9)))


class GeoTest(unittest.TestCase):
    def test_bearing_and_heading(self):
        self.assertAlmostEqual(geo.bearing_deg(32.93, -97.08, 32.93, -96.0), 90, delta=1)
        self.assertTrue(geo.within_heading(122, 90, 60))
        self.assertFalse(geo.within_heading(24, 90, 60))
        self.assertTrue(geo.within_heading(350, 10, 30))  # wraps past north


SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "reserveamerica", "explore_page.html")


def ra_page(records, total_pages=1, any_available=True):
    state = {"backend": {"productSearch": {"searchResults": {
        "totalPages": total_pages, "records": records,
        "summary": {"atLeastOneSiteAvailable": any_available}}}}}
    return f'<html><script type="application/json" id="initialState">{json.dumps(state)}</script></html>'


def ra_record(name, group, statuses, amps=None, use="NIGHTLY"):
    attrs = [{"name": "Electricity Hookup", "value": [amps]}] if amps else []
    return {
        "name": name, "prodGrpName": group, "prodInfo": {"typeOfUse": use},
        "details": {"loopName": "BIG PINE", "ratesStartingFrom": "$25.00", "attributes": attrs},
        "availabilityGrid": [{"date": d, "status": st} for d, st in statuses],
    }


FRI_SAT = [("2026-10-23", "AVAILABLE"), ("2026-10-24", "AVAILABLE")]


class TexasTest(unittest.TestCase):
    def test_real_tyler_page(self):
        """Captured Tyler SP page for Fri Oct 23, 2026: 127 sites, none open that night."""
        with open(SAMPLE, encoding="utf-8") as f:
            results = texas.parse_search_page(f.read())
        self.assertEqual(results["totalRecords"], 127)
        self.assertEqual(len(results["records"]), 20)
        rec = results["records"][0]
        self.assertTrue(texas.is_electric(rec))
        self.assertEqual(texas._attribute(rec, "Electricity Hookup"), "50")
        self.assertEqual(texas.open_sites(results["records"], date(2026, 10, 23), date(2026, 10, 24)), [])

    def test_real_page_short_circuits_when_full(self):
        with open(SAMPLE, encoding="utf-8") as f:
            page = f.read()
        fetch = mock.Mock(return_value=page)
        park = texas.PARKS[4]
        sites = texas.available_sites(park, date(2026, 10, 23), date(2026, 10, 24), fetch=fetch, delay=0)
        self.assertEqual(sites, [])
        self.assertEqual(fetch.call_count, 1)
        self.assertIn("arrivalDate=2026-10-23&lengthOfStay=1&pageNumber=0", fetch.call_args[0][0])

    def test_open_electric_sites_across_pages(self):
        page0 = ra_page([
            ra_record("A1", "Campsite Electric", FRI_SAT, amps="30"),
            ra_record("A2", "Campsite with Water", FRI_SAT),
            ra_record("A3", "Campsite Full Hookup", [("2026-10-23", "AVAILABLE"), ("2026-10-24", "RESERVED")]),
        ], total_pages=2)
        page1 = ra_page([
            ra_record("B1", "Campsite Full Hookup", FRI_SAT, amps="50"),
            ra_record("B2", "Pavilion", FRI_SAT, amps="20", use="DAY"),
        ], total_pages=2)
        fetch = mock.Mock(side_effect=[page0, page1])
        sites = texas.available_sites(texas.PARKS[0], date(2026, 10, 23), date(2026, 10, 25),
                                      electric_only=True, fetch=fetch, delay=0)
        self.assertEqual([s.name for s in sites], ["A1", "B1"])
        self.assertEqual(sites[1].electric_amps, "50")
        self.assertEqual(sites[0].loop, "Big Pine")
        self.assertIn("pageNumber=1", fetch.call_args_list[1][0][0])

    def test_hides_specialty_sites_but_not_tent_only(self):
        night = [("2026-10-23", "AVAILABLE")]
        records = [
            ra_record("GN003", "Campsite Electric - Tent Only", night, amps="30"),
            ra_record("H1", "Campsite Equestrian Electric", night, amps="30"),
            ra_record("C1", "Cabin", night, amps="30"),
        ]
        records[0]["details"]["loopName"] = "GRANNY'S NECK SHELTER AREA"
        sites = texas.open_sites(records, date(2026, 10, 23), date(2026, 10, 24), electric_only=True)
        self.assertEqual([s.name for s in sites], ["GN003"])  # "Shelter" in the loop name doesn't count
        self.assertEqual(sites[0].loop, "Granny's Neck Shelter Area")

    def test_electric_detection(self):
        self.assertTrue(texas.is_electric(ra_record("x", "Campsite with Water", [], amps="30")))
        self.assertFalse(texas.is_electric(ra_record("x", "Campsite with Water", [])))
        self.assertFalse(texas.is_electric(ra_record("x", "Cabin", [], amps="30")))
        self.assertFalse(texas.is_electric(ra_record("x", "Campsite Nonelectric", [])))

    def test_blocked_page_raises(self):
        with self.assertRaises(ValueError):
            texas.parse_search_page("<html>Please verify you are a human</html>")


class EndToEndTest(unittest.TestCase):
    def test_main_prints_hits(self):
        search = {"total": 1, "results": [
            {"entity_id": "10", "name": "PINE LAKE", "latitude": "40.0", "longitude": "-79.0"}]}

        def fake(path, params=None):
            return search if path == "/api/search" else OCT

        with mock.patch.object(recgov, "_get_json", side_effect=fake), \
                mock.patch.object(texas, "_fetch") as ra, \
                mock.patch("builtins.print") as p:
            rc = cli.main(["--lat", "40", "--lon", "-81", "--start", "2026-10-23", "--electric"])
        out = "\n".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertEqual(rc, 0)
        self.assertIn("Pine Lake", out)
        self.assertIn("site A01", out)
        self.assertNotIn("A02", out)
        self.assertNotIn("State Park", out)  # (40, -79) is nowhere near Texas
        ra.assert_not_called()

    def test_main_checks_state_parks(self):
        def fake(path, params=None):
            return {"total": 0, "results": []}

        page = ra_page([ra_record("T7", "Campsite Electric", [("2026-10-23", "AVAILABLE")], amps="30")])
        with mock.patch.object(recgov, "_get_json", side_effect=fake), \
                mock.patch.object(texas, "_fetch", return_value=page), \
                mock.patch("builtins.print") as p:
            rc = cli.main(["--lat", "32.9343", "--lon", "-97.0781",  # Grapevine
                           "--start", "2026-10-23", "--nights", "1", "--electric"])
        out = "\n".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertEqual(rc, 0)
        self.assertIn("Lake Tawakoni State Park", out)
        self.assertIn("site T7: Campsite Electric, 30 amp", out)
        # 2 hours east of Grapevine: Tawakoni, Purtis Creek, Cooper Lake, Tyler; not Texoma (north),
        # Cedar Hill (south) or Daingerfield (too far).
        for name in ("Lake Tawakoni", "Purtis Creek", "Cooper Lake State Park - South Sulphur", "Tyler", "Bonham"):
            self.assertIn(name, out)
        for name in ("Eisenhower", "Cedar Hill", "Daingerfield", "Ray Roberts", "Mineral Wells", "Whitney"):
            self.assertNotIn(name, out)

    def test_any_direction_includes_ray_roberts(self):
        near = [p.name for p in texas.PARKS if geo.haversine_mi(32.9343, -97.0781, p.lat, p.lon) <= 110]
        self.assertIn("Ray Roberts Lake State Park - Isle du Bois", near)
        self.assertIn("Ray Roberts Lake State Park - Johnson Branch", near)
        self.assertEqual(len(near), 20)
        self.assertEqual(len({p.park_id for p in texas.PARKS}), len(texas.PARKS))

    def test_recgov_filtered_to_east_and_sorted_nearest_first(self):
        search = {"total": 3, "results": [
            {"entity_id": "1", "name": "TEXOMA NORTH", "latitude": "33.85", "longitude": "-96.6"},
            {"entity_id": "2", "name": "JIM CHAPMAN", "latitude": "33.30", "longitude": "-95.62"},
            {"entity_id": "3", "name": "LAVON", "latitude": "33.03", "longitude": "-96.48"},
        ]}
        checked = []

        def fake(path, params=None):
            if path == "/api/search":
                return search
            checked.append(path.split("/")[-2])
            return {"campsites": {}}

        with mock.patch.object(recgov, "_get_json", side_effect=fake), mock.patch("builtins.print"):
            cli.main(["--lat", "32.9343", "--lon", "-97.0781", "--no-state-parks", "--workers", "1",
                      "--start", "2026-10-23", "--nights", "1"])
        self.assertEqual(checked, ["3", "2"])


class RouteTest(unittest.TestCase):
    SA, AUSTIN, DALLAS = (29.42, -98.49), (30.27, -97.74), (32.78, -96.80)

    def test_route_position(self):
        route = [self.SA, self.AUSTIN, self.DALLAS]
        off, along = geo.route_position(30.31, -98.25, route)  # Pedernales Falls, west of Austin
        self.assertAlmostEqual(off, 26, delta=4)
        self.assertAlmostEqual(along, 57, delta=6)
        off, along = geo.route_position(*self.DALLAS, route)
        self.assertLess(off, 0.5)
        self.assertAlmostEqual(along, geo.haversine_mi(*self.SA, *self.AUSTIN)
                               + geo.haversine_mi(*self.AUSTIN, *self.DALLAS), delta=5)

    def test_points_along(self):
        pts = geo.points_along([self.SA, self.DALLAS], 60)
        self.assertEqual(pts[0], self.SA)
        self.assertEqual(pts[-1], self.DALLAS)
        gaps = [geo.haversine_mi(*a, *b) for a, b in zip(pts, pts[1:])]
        self.assertTrue(all(g <= 60 for g in gaps))

    def test_route_mode_end_to_end(self):
        towns = {"San Antonio, TX": self.SA, "Blanco, TX": (30.10, -98.42), "Austin, TX": self.AUSTIN,
                 "Dallas, TX": self.DALLAS}
        search = {"total": 2, "results": [
            {"entity_id": "1", "name": "POTTERS CREEK", "latitude": "29.90", "longitude": "-98.27"},  # Canyon Lake
            {"entity_id": "2", "name": "FAR WEST", "latitude": "30.5", "longitude": "-100.5"},
        ]}

        def fake(path, params=None):
            return search if path == "/api/search" else OCT

        page = ra_page([ra_record("012", "Campsite Electric", [("2026-11-27", "AVAILABLE"),
                                                               ("2026-11-28", "AVAILABLE")], amps="50")])
        with mock.patch.object(geo, "geocode", side_effect=towns.get), mock.patch("time.sleep"), \
                mock.patch.object(recgov, "_get_json", side_effect=fake), \
                mock.patch.object(texas, "_fetch", return_value=page) as ra, \
                mock.patch.object(hipcamp, "lands_near", return_value=([], [])), \
                mock.patch.object(campspot, "parks_near", return_value=([], [])), \
                mock.patch("builtins.print") as p:
            rc = cli.main(["--route", "San Antonio, TX", "Austin, TX", "Dallas, TX",
                           "--route", "San Antonio, TX", "Blanco, TX", "Dallas, TX",
                           "--start", "2026-11-27", "--nights", "2", "--electric", "--workers", "1"])
        out = "\n".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertEqual(rc, 0)
        self.assertIn("Guadalupe River State Park  (30 mi along the route, 3 mi off it)", out)
        checked = {c[0][0].split("/explore/")[1].split("/")[0] for c in ra.call_args_list}
        self.assertIn("guadalupe-river-state-park", checked)
        self.assertIn("inks-lake-state-park", checked)
        self.assertIn("enchanted-rock-state-natural-area", checked)  # only near the Blanco route
        self.assertNotIn("garner-state-park", checked)
        self.assertNotIn("lake-arrowhead-state-park", checked)
        self.assertNotIn("Far West", out)

    def test_route_labels(self):
        r = texas.StateParkResult(texas.PARKS[0], 64.4, 8.2)
        self.assertEqual(cli.where(r), "64 mi along the route, 8 mi off it")
        self.assertEqual(cli.where(texas.StateParkResult(texas.PARKS[0], 22.0)), "22 mi straight-line")

    def test_route_needs_two_places(self):
        with self.assertRaises(SystemExit), mock.patch("sys.stderr"):
            cli.parse_args(["--route", "Austin, TX"])


HIPCAMP_SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "private", "hipcamp_canyon_lake.html")


class HipcampTest(unittest.TestCase):
    def test_town_page(self):
        self.assertEqual(hipcamp.town_page("Canyon Lake, TX"),
                         "https://www.hipcamp.com/en-US/d/united-states/texas/canyon-lake/camping/all")
        self.assertIsNone(hipcamp.town_page("Austin"))
        self.assertIsNone(hipcamp.town_page("Boise, ID"))

    def test_real_canyon_lake_page(self):
        with open(HIPCAMP_SAMPLE, encoding="utf-8") as f:
            lands = hipcamp.parse_town_page(f.read())
        self.assertEqual(len(lands), 20)
        juniper = next(l for l in lands if l.name == "The Juniper Ranch & Retreat")
        self.assertTrue(juniper.lodging_only)
        self.assertFalse(juniper.electric)
        b2 = next(l for l in lands if l.name == "B2 Hideaway")
        self.assertTrue(b2.electric)
        self.assertFalse(b2.lodging_only)
        self.assertEqual(b2.recommends_pct, 100)
        self.assertEqual(b2.url(date(2026, 11, 27), date(2026, 11, 29)),
                         "https://www.hipcamp.com" + b2.path + "?arrive=2026-11-27&depart=2026-11-29")

    def test_page_without_listings_is_empty_not_an_error(self):
        page = '<script id="__NEXT_DATA__" type="application/json">{"props":{"pageProps":{"other":1}}}</script>'
        self.assertEqual(hipcamp.parse_town_page(page), [])

    def test_lands_near_dedupes_and_reports_errors(self):
        with open(HIPCAMP_SAMPLE, encoding="utf-8") as f:
            page = f.read()

        def fetch(url):
            if "blanco" in url:
                raise OSError("boom")
            return page

        lands, errors = hipcamp.lands_near(["Canyon Lake, TX", "Johnson City, TX", "Blanco, TX", "Austin"], fetch=fetch)
        self.assertEqual(len(lands), 20)
        self.assertEqual(errors, ["Hipcamp (Blanco, TX): boom"])

    def test_cli_lists_private_electric_campgrounds(self):
        with open(HIPCAMP_SAMPLE, encoding="utf-8") as f:
            page = f.read()
        towns = {"San Antonio, TX": (29.42, -98.49), "Canyon Lake, TX": (29.88, -98.27), "Austin, TX": (30.27, -97.74)}
        with mock.patch.object(geo, "geocode", side_effect=towns.get), mock.patch("time.sleep"), \
                mock.patch.object(recgov, "_get_json", return_value={"total": 0, "results": []}), \
                mock.patch.object(web, "fetch_text", return_value=page), \
                mock.patch("builtins.print") as p:
            cli.main(["--route", "San Antonio, TX", "Canyon Lake, TX", "Austin, TX", "--no-state-parks",
                      "--start", "2026-11-27", "--nights", "2", "--electric"])
        out = "\n".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertIn("B2 Hideaway", out)
        self.assertIn("100% recommend", out)
        self.assertIn("arrive=2026-11-27&depart=2026-11-29", out)
        self.assertNotIn("The Juniper Ranch", out)  # lodging only, no electric


CAMPSPOT_AREA = os.path.join(os.path.dirname(__file__), "..", "samples", "private", "campspot_near_canyon_lake.html")
CAMPSPOT_PARK = os.path.join(os.path.dirname(__file__), "..", "samples", "private", "campspot_park_fimfo.html")


def campspot_type(name, category, amenities, statuses, avg=None, low=50):
    return {"id": 1, "name": name, "campsiteCategoryCode": category, "amenities": amenities,
            "availability": "AVAILABLE" if "AVAILABLE" in statuses else "UNAVAILABLE",
            "averagePricePerNight": avg, "lowestBaselinePrice": low, "failureReasons": [],
            "campsites": [{"id": i, "name": f"S{i}", "availability": s, "amenities": amenities}
                          for i, s in enumerate(statuses)]}


class CampspotTest(unittest.TestCase):
    def test_area_page_and_park_id(self):
        self.assertEqual(campspot.area_page("Canyon Lake, TX"),
                         "https://www.campspot.com/c/camping-in-texas/near-canyon-lake")
        self.assertIsNone(campspot.area_page("Canyon Lake"))
        with open(CAMPSPOT_AREA, encoding="utf-8") as f:
            parks = campspot.parse_area_page(f.read())
        self.assertEqual(len(parks), 10)
        cranes = next(p for p in parks if p.slug == "cranes-mill-rv-park-canyon-lake-tx")
        self.assertAlmostEqual(cranes.lat, 29.892, places=2)
        self.assertEqual(cranes.starting_price, "$50")
        with open(CAMPSPOT_PARK, encoding="utf-8") as f:
            self.assertEqual(campspot.parse_park_id(f.read()), 55)

    def test_parse_availability(self):
        data = [
            campspot_type("Premium Lakefront RV Site", "rv", ["30-Amp", "50-Amp", "Electricity"],
                          ["AVAILABLE", "UNAVAILABLE", "AVAILABLE"], avg=72.5),
            campspot_type("Primitive Tent", "tent", ["Fire Ring"], ["AVAILABLE"]),
            campspot_type("Preferred Tent Site", "tent", ["20-Amp", "Water Hook-Up"], ["UNAVAILABLE"]),
            campspot_type("Bluebonnet Cabin", "lodging", ["Electricity"], ["AVAILABLE"]),
            campspot_type("Group Site", "tent", ["30-Amp"], ["AVAILABLE"]),
        ]
        sites = campspot.parse_availability(data, electric_only=True)
        self.assertEqual([(s.name, s.open_count, s.amps, s.price_per_night) for s in sites],
                         [("Premium Lakefront RV Site", 2, "30/50", 72.5)])
        everything = campspot.parse_availability(data, standard_only=False)
        self.assertEqual({s.name for s in everything},
                         {"Premium Lakefront RV Site", "Primitive Tent", "Bluebonnet Cabin", "Group Site"})
        with self.assertRaises(ValueError):
            campspot.parse_availability({"error": "nope"})

    def test_available_sites_requests(self):
        with open(CAMPSPOT_PARK, encoding="utf-8") as f:
            page = f.read()
        api = json.dumps([campspot_type("Standard Tent Site", "tent", ["20-Amp"], ["AVAILABLE"])])
        fetch = mock.Mock(side_effect=[page, api])
        park = campspot.Park("Camp Fimfo", "camp-fimfo", 29.86, -98.16)
        sites = campspot.available_sites(park, date(2026, 11, 27), date(2026, 11, 29), electric_only=True,
                                         fetch=fetch, pause=0)
        self.assertEqual([s.name for s in sites], ["Standard Tent Site"])
        url = fetch.call_args_list[1][0][0]
        self.assertTrue(url.startswith("https://www.campspot.com/api/gator-core/v2/availability/parks/55?"))
        self.assertIn("checkin=2026-11-27&checkout=2026-11-29", url)
        self.assertEqual(fetch.call_args_list[1][1]["headers"]["x-client-type"], "AGGREGATOR")

    def test_cli_section(self):
        with open(CAMPSPOT_AREA, encoding="utf-8") as f:
            area = f.read()
        with open(CAMPSPOT_PARK, encoding="utf-8") as f:
            park_page = f.read()
        api = json.dumps([campspot_type("Premium Lakefront RV Site", "rv", ["30-Amp", "Electricity"],
                                        ["AVAILABLE"], avg=80)])

        def fetch(url, timeout=40, headers=None):
            if "/c/camping-in-texas/" in url:
                return area
            if "/api/gator-core/" in url:
                return api
            if "/park/" in url:
                return park_page
            raise OSError("not stubbed")

        towns = {"San Antonio, TX": (29.42, -98.49), "Canyon Lake, TX": (29.88, -98.27), "Austin, TX": (30.27, -97.74)}
        with mock.patch.object(geo, "geocode", side_effect=towns.get), mock.patch("time.sleep"), \
                mock.patch.object(recgov, "_get_json", return_value={"total": 0, "results": []}), \
                mock.patch.object(web, "fetch_text", side_effect=fetch), \
                mock.patch.object(hipcamp, "lands_near", return_value=([], [])), \
                mock.patch("builtins.print") as p:
            rc = cli.main(["--route", "San Antonio, TX", "Canyon Lake, TX", "Austin, TX", "--no-state-parks",
                           "--start", "2026-11-27", "--nights", "2", "--electric"])
        out = "\n".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertIn("private campground(s) on Campspot with sites open all 2 night(s)", out)
        self.assertIn("Cranes Mill RV Park - Canyon Lake", out)
        self.assertIn("- Premium Lakefront RV Site (rv, 30 amp): 1 open  $80/night", out)
        self.assertIn("cranes-mill-rv-park-canyon-lake-tx?checkin=2026-11-27&checkout=2026-11-29", out)
        self.assertEqual(rc, 0)


class WebTest(unittest.TestCase):
    def test_curl_fallback_on_tls_error(self):
        import ssl
        import urllib.error
        err = urllib.error.URLError(ssl.SSLError(1, "[SSL: TLSV1_ALERT_PROTOCOL_VERSION]"))
        done = mock.Mock(stdout=b"<html>ok</html>")
        with mock.patch("urllib.request.urlopen", side_effect=err), \
                mock.patch("shutil.which", return_value="/usr/bin/curl"), \
                mock.patch("subprocess.run", return_value=done) as run:
            self.assertEqual(web.fetch_text("https://www.campspot.com/x"), "<html>ok</html>")
        self.assertEqual(run.call_args[0][0][0], "curl")
        self.assertEqual(run.call_args[0][0][-1], "https://www.campspot.com/x")

    def test_other_errors_are_not_retried(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no route")), \
                mock.patch("subprocess.run") as run:
            with self.assertRaises(urllib.error.URLError):
                web.fetch_text("https://example.com")
        run.assert_not_called()


class SnapshotTest(unittest.TestCase):
    def test_recgov_site_nights(self):
        with mock.patch.object(recgov, "_get_json", return_value=OCT):
            rows = recgov.site_nights("x", date(2026, 10, 23), date(2026, 10, 25))
        got = {s.name: nights for s, nights in rows}
        self.assertEqual(got["A01"], ["2026-10-23", "2026-10-24"])
        self.assertEqual(got["B01"], ["2026-10-23"])  # partially open still listed
        self.assertNotIn("C01", got)  # day use

    def test_texas_site_nights_reads_every_page(self):
        page0 = ra_page([ra_record("A1", "Campsite Electric", [("2026-10-23", "RESERVED"),
                                                               ("2026-10-24", "AVAILABLE")], amps="30")],
                        total_pages=2, any_available=False)
        page1 = ra_page([ra_record("B1", "Campsite with Water", [("2026-10-23", "AVAILABLE")])], total_pages=2)
        fetch = mock.Mock(side_effect=[page0, page1])
        rows = texas.site_nights(texas.PARKS[0], date(2026, 10, 23), 3, fetch=fetch, delay=0)
        self.assertEqual(fetch.call_count, 2)  # no early exit: other nights may be open
        self.assertIn("arrivalDate=2026-10-23&lengthOfStay=1", fetch.call_args_list[0][0][0])
        self.assertEqual([(s.name, electric, nights) for s, electric, nights in rows],
                         [("A1", True, ["2026-10-24"]), ("B1", False, ["2026-10-23"])])

    def test_real_tyler_page_finds_later_nights(self):
        with open(SAMPLE, encoding="utf-8") as f:
            page = f.read()
        rows = texas.site_nights(texas.PARKS[4], date(2026, 10, 23), 14, fetch=lambda url: page, delay=0)
        self.assertTrue(rows)  # Friday was full, but the grid has open nights later on
        self.assertTrue(all(n > "2026-10-23" for _, _, nights in rows for n in nights))

    def test_build(self):
        search = {"total": 2, "results": [
            {"entity_id": "3", "name": "LAVON", "latitude": "33.03", "longitude": "-96.48"},
            {"entity_id": "9", "name": "FAR AWAY", "latitude": "35.5", "longitude": "-97.0"},
        ]}

        def fake(path, params=None):
            return search if path == "/api/search" else OCT

        page = ra_page([ra_record("T7", "Campsite Electric", [("2026-10-23", "AVAILABLE")], amps="30")])
        args = snapshot.parse_args(["--lat", "32.9343", "--lon", "-97.0781", "--out", "x.json", "--days", "3"])
        with mock.patch.object(recgov, "_get_json", side_effect=fake), \
                mock.patch.object(texas, "_fetch", return_value=page), mock.patch("time.sleep"):
            snap = snapshot.build(args, today=date(2026, 10, 23))
        self.assertEqual(snap["first_night"], "2026-10-23")
        self.assertEqual(snap["last_night"], "2026-10-25")
        self.assertEqual(snap["checked"]["recreation_gov"], 1)
        self.assertEqual(snap["checked"]["state_parks"], 20)
        lavon = next(c for c in snap["campgrounds"] if c["name"] == "Lavon")
        self.assertEqual(lavon["heading"], "E")
        tyler = next(c for c in snap["campgrounds"] if c["name"] == "Tyler State Park")
        self.assertEqual(tyler["sites"][0]["open"], ["2026-10-23"])
        self.assertIn("{arrival}", tyler["booking_url_template"])
        self.assertEqual(snap["campgrounds"], sorted(snap["campgrounds"], key=lambda c: c["miles"]))
        json.dumps(snap)


if __name__ == "__main__":
    unittest.main()
