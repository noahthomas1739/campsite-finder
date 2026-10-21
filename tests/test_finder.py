import json
import os
import unittest
from datetime import date
from unittest import mock

from campsite_finder import cli, geo, recgov, texas


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
        for name in ("Lake Tawakoni", "Purtis Creek", "Cooper Lake State Park - South Sulphur", "Tyler"):
            self.assertIn(name, out)
        for name in ("Eisenhower", "Cedar Hill", "Daingerfield", "Ray Roberts"):
            self.assertNotIn(name, out)

    def test_any_direction_includes_ray_roberts(self):
        near = [p.name for p in texas.PARKS if geo.haversine_mi(32.9343, -97.0781, p.lat, p.lon) <= 110]
        self.assertIn("Ray Roberts Lake State Park - Isle du Bois", near)
        self.assertIn("Ray Roberts Lake State Park - Johnson Branch", near)

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


if __name__ == "__main__":
    unittest.main()
