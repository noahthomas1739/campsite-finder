# campsite-finder

Stop clicking through every campground page. This searches Recreation.gov for
campgrounds around a point a few hours' drive from you, then checks which sites
are open **every night** of your stay. It can limit results to sites with
**electric hookups**.

No dependencies. You only need Python 3.10 or newer.

## Quick start

```bash
git clone <this repo> && cd campsite-finder

# This weekend (Fri -> Sun), ~2 hours east of you, electric sites only
python -m campsite_finder --from "Columbus, OH" --drive-hours 2 --direction east --electric
```

Example output:

```
3 campground(s) with sites open all 2 night(s):

Pine Lake  (104 mi straight-line; Somewhere, PA)
  4 site(s) open  ->  https://www.recreation.gov/camping/campgrounds/123456
    - Loop A site A01: Standard Electric  https://www.recreation.gov/camping/campsites/98765
    ...
```

Click the link and book. Availability changes fast, so book soon after you find a site.

## DFW: about 2 hours east

```bash
python -m campsite_finder --from "Dallas, TX" --direction east --radius 60 --electric
```

A 60-mile radius around the point about 100 miles east of Dallas covers the I-20 and I-30 corridors:

- **Recreation.gov (live availability is checked):** Army Corps of Engineers lakes in range, such as
  Jim Chapman (Cooper) Lake and Lake O' the Pines.
- **Texas State Parks (booking links only):** Lake Tawakoni, Cooper Lake (South Sulphur and
  Doctors Creek), Tyler, Lake Bob Sandlin, and Daingerfield. Add `--radius 75` to include Purtis Creek.

If you're starting from Fort Worth, use `--from "Fort Worth, TX"` and the drive math shifts accordingly.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--from "City, ST"` / `--lat --lon` | required | Where you're starting |
| `--drive-hours` | 2 | How far you want to go |
| `--mph` | 50 | Average straight-line progress per hour. Lower it for mountain roads |
| `--direction` | east | north, ne, east, se, south, sw, west, nw, or `any` (a circle around you) |
| `--radius` | 40 | Miles to search around the target point |
| `--start` | this Friday | Check-in date `YYYY-MM-DD` |
| `--nights` | through Sunday | Number of nights |
| `--electric` | off | Only sites with an electric hookup |
| `--max-campgrounds` | 60 | Cap on campgrounds checked |
| `--show-sites` | 5 | Sites listed per campground |
| `--no-state-parks` | off | Hide the Texas State Parks links |

The exit code is 0 when something is found and 1 when nothing is, so you can
run it from cron as an alert.

## How it works and its limits

- Geocoding uses OpenStreetMap Nominatim.
- Campground search and availability use the same JSON endpoints that the
  recreation.gov website calls. These endpoints are unofficial and can change.
- "2 hours east" means a point `drive-hours × mph` miles due east, plus a
  `--radius` circle around it. This is a straight-line estimate, not real
  driving time.
- Electric sites are found from recreation.gov's site type (`STANDARD
  ELECTRIC`, `RV ELECTRIC`, ...).
- **Coverage:** live availability is checked for recreation.gov only. That
  includes federal sites such as National Forests, Army Corps of Engineers
  lakes, and National Parks.
- **Texas State Parks** book through texasstateparks.reserveamerica.com. That
  site has no public availability API, so `campsite_finder/texas.py` keeps a
  list of East Texas and DFW-area parks and prints a booking link for each one
  in your search area. Availability isn't checked. To add a park, copy the
  `parkId=` number from its ReserveAmerica page into `PARKS`.

## Tests

```bash
python -m unittest discover -s tests -t .
```
