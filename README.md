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

- **Texas State Parks:** Lake Tawakoni (~63 mi), Bonham (~69 mi), Purtis Creek (~75 mi), Cooper
  Lake (both units, ~85 mi), and Tyler (~109 mi).
- **Recreation.gov:** Army Corps of Engineers lakes to the east, such as Lavon Lake and Jim
  Chapman Lake.

It leaves out Ray Roberts and Lake Texoma (north), Cedar Hill (south), and the parks past Tyler. Lake Bob
Sandlin, Daingerfield, and Lake O' the Pines are 2¼ hours or more. To include them, add
`--drive-hours 2.5`.

To search every direction, use `--direction any`. That checks all 20 state parks within about
2 hours of Grapevine:

| Direction | State parks |
|---|---|
| East / NE | Lake Tawakoni, Bonham, Purtis Creek, Cooper Lake (both units), Tyler |
| North | Ray Roberts Lake (Isle du Bois, Johnson Branch), Eisenhower (Lake Texoma) |
| West / NW | Lake Mineral Wells, Fort Richardson, Possum Kingdom, Palo Pinto Mountains, Lake Arrowhead |
| South / SW | Cedar Hill, Cleburne, Dinosaur Valley, Lake Whitney, Meridian, Fort Parker |

Mother Neff, Lake Bob Sandlin, and Daingerfield are also in the list. They're just past
2 hours, so they appear with `--drive-hours 2.5`. A search in every direction loads more pages,
so it takes a few minutes.

## Web page (GitHub Pages)

`site/index.html` is a page anyone can open to see open sites without running anything. A
scheduled GitHub Actions job (`.github/workflows/update-site.yml`) runs every 6 hours. It checks
every campground within about 2 hours of Grapevine, in all directions, for the next 14 nights,
using `python -m campsite_finder.snapshot`. It then publishes the page together with the results
(`data.json`). On the page, visitors pick the arrival night, number of nights, direction, maximum
distance, and whether to show electric sites only.

One-time setup: in the repo, go to **Settings → Pages → Build and deployment → Source** and
choose **GitHub Actions**. Then open the **Actions** tab, pick **Update campsite page**, and click
**Run workflow**. The page will be at `https://<owner>.github.io/campsite-finder/`.

To change the starting point or distance, edit the `snapshot` command in the workflow file.

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
| `--all-site-types` | off | Include horse, group, pavilion, picnic, shelter and cabin sites, which are hidden by default |
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
