import unittest
from datetime import date
from unittest import mock

from campsite_finder import cli, geo, recgov


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
    def test_east_point_distance(self):
        lat, lon = geo.destination_point(39.96, -83.0, 90, 100)
        self.assertAlmostEqual(geo.haversine_mi(39.96, -83.0, lat, lon), 100, delta=0.5)
        self.assertGreater(lon, -83.0)


class EndToEndTest(unittest.TestCase):
    def test_main_prints_hits(self):
        search = {"total": 1, "results": [
            {"entity_id": "10", "name": "PINE LAKE", "latitude": "40.0", "longitude": "-79.0"}]}

        def fake(path, params=None):
            return search if path == "/api/search" else OCT

        with mock.patch.object(recgov, "_get_json", side_effect=fake), \
                mock.patch("builtins.print") as p:
            rc = cli.main(["--lat", "40", "--lon", "-81", "--start", "2026-10-23", "--electric"])
        out = "\n".join(str(c.args[0]) for c in p.call_args_list if c.args)
        self.assertEqual(rc, 0)
        self.assertIn("Pine Lake", out)
        self.assertIn("site A01", out)
        self.assertNotIn("A02", out)


if __name__ == "__main__":
    unittest.main()
