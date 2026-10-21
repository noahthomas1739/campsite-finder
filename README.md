# campsite-finder

Stop clicking through every campground page. This searches Recreation.gov for
campgrounds around a point a few hours' drive from you, then checks which sites
are open **every night** of your stay. It can limit results to sites with
**electric hookups**.

No dependencies. You only need Python 3.9 or newer.

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

## Grapevine / DFW: anywhere within 2 hours, to the east

```bash
python3 -m campsite_finder --from "Grapevine, TX" --electric
```

This searches everything **from your doorstep out to about 2 hours' drive**, and keeps only places
**northeast through southeast** of you. Places 30 minutes away count too. Add `--nights 1` for
Friday night only.

From Grapevine, that covers:

- **Texas State Parks:** Lake Tawakoni (~63 mi), Purtis Creek (~75 mi), Cooper Lake (both units,
  ~85 mi), and Tyler (~109 mi).
- **Recreation.gov:** Army Corps of Engineers lakes to the east, such as Lavon Lake and Jim
  Chapman Lake.

It leaves out Lake Texoma (north), Cedar Hill (south), and the parks past Tyler. Lake Bob
Sandlin, Daingerfield, and Lake O' the Pines are 2¼ hours or more. To include them, add
`--drive-hours 2.5`.

## Options

| Flag | Default | Meaning |
|---|---|---|
| `--from "City, ST"` / `--lat --lon` | required | Where you're starting |
| `--drive-hours` | 2 | Furthest you're willing to drive. Anything closer counts too |
| `--mph` | 55 | Straight-line miles per hour of driving, used to turn hours into miles |
| `--direction` | east | Only places this way from you: north, ne, east, se, south, sw, west, nw, or `any` |
| `--spread` | 60 | Degrees either side of the direction. 60 means NE through SE for east |
| `--start` | this Friday | Check-in date `YYYY-MM-DD` |
| `--nights` | through Sunday | Number of nights |
| `--electric` | off | Only sites with an electric hookup |
| `--max-campgrounds` | 80 | Cap on Recreation.gov campgrounds checked, nearest first |
| `--show-sites` | 5 | Sites listed per campground |
| `--no-state-parks` | off | Skip checking Texas State Parks |

The exit code is 0 when something is found and 1 when nothing is, so you can
run it from cron as an alert.

## How it works and its limits

- Geocoding uses OpenStreetMap Nominatim.
- Campground search and availability use the same JSON endpoints that the
  recreation.gov website calls. These endpoints are unofficial and can change.
- "Within 2 hours, east" means within `drive-hours × mph` straight-line miles
  of you, and within `--spread` degrees of due east. This estimates driving
  time; it doesn't use real road routes.
- Electric sites are found from recreation.gov's site type (`STANDARD
  ELECTRIC`, `RV ELECTRIC`, ...).
- **Coverage:** live availability is checked for recreation.gov only. That
  includes federal sites such as National Forests, Army Corps of Engineers
  lakes, and National Parks.
- **Texas State Parks** book through ReserveAmerica, which has no public API.
  Its campsite search page (`reserveamerica.com/explore/<park>/TX/<id>/campsites`)
  embeds its results as JSON, including each site's type, hookups and nightly
  availability. `campsite_finder/texas.py` reads that JSON, 20 sites per page.
  This is scraping, so it breaks if ReserveAmerica changes its page. When that
  happens, run `python3 tools/capture_reserveamerica.py` to save fresh pages.
  `campsite_finder/texas.py` keeps a list of East Texas and DFW-area parks. To
  add one, copy the `parkId=` number from its ReserveAmerica page into `PARKS`.

## Tests

```bash
python -m unittest discover -s tests -t .
```
