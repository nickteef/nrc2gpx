# NRC2GPX

**Export your Nike Run Club runs as GPX files.** Free your running history from the NRC app and import it into Strava, Garmin Connect, Komoot or any other tool that reads GPX.

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/verified%20working-November%202026-brightgreen)

> ✅ **Verified working in November 2026.** NRC2GPX relies on Nike's undocumented API, which changes from time to time. Older exporters stopped working because of those changes. If this tool stops working for you, please [open an issue](../../issues).

---

## Features

- **List** all your runs with date, distance, duration, pace and GPS availability
- **Export** every run with GPS data to a separate `.gpx` file
- **Latest only**: export just your most recent run, or the last *N* runs
- **Date range**: export runs between two dates
- **Interactive picker**: choose runs from a numbered list (`1,3,5-8`)
- **By ID**: export specific activities
- **Incremental**: already exported runs are skipped, so you can re-run it any time
- Includes **elevation** data when NRC recorded it
- One dependency (`requests`), works on Windows, macOS and Linux

## Requirements

- Python 3.9 or newer
- A Nike account with runs recorded in Nike Run Club

## Installation

```bash
pip install git+https://github.com/nickteef/nrc2gpx.git
```

Or clone the repo and install it locally:

```bash
git clone https://github.com/nickteef/nrc2gpx.git
cd nrc2gpx
pip install .
```

> **Windows tip:** if `nrc2gpx` is "not recognized as an internal or external command", pip's Scripts folder isn't on your `PATH`. Use `python -m nrc2gpx` instead. It works exactly the same.

## Getting your access token

NRC has no official export, so NRC2GPX uses the same access token as Nike's website. The token **expires after about one hour**, so get a fresh one each time you use the tool.

First, open [nike.com](https://www.nike.com) in a desktop browser, **log in** with the account you use in NRC, and open the developer tools (`F12`, or `Ctrl+Shift+I` / `Cmd+Option+I`).

### Option A: Console (quickest)

Switch to the **Console** tab, paste this line and press Enter:

```js
copy(Object.keys(localStorage).filter(k => k.startsWith("oidc.user:")).map(k => JSON.parse(localStorage.getItem(k)).access_token)[0])
```

The token is now in your clipboard. Paste it after `-t`.

> Chrome may block pasting into the console the first time. Type `allow pasting`, press Enter, then paste again. If the command prints `undefined` or nothing ends up in your clipboard, use option B.

### Option B: Network tab

1. Switch to the **Network** tab, refresh the page and type `api.nike.com` into the filter box.
2. Click any request that has an **`Authorization`** request header.
3. Copy the value after `Bearer `. It is a long string starting with `eyJ...`.

> 🔒 **Treat the token like a password.** For the next hour it gives access to your Nike account. Don't paste it into issues, screenshots or shared chats.

## Usage

```bash
# See what's in your account
nrc2gpx list -t YOUR_TOKEN

# Export every run with GPS data (into ./nrc_gpx)
nrc2gpx export -t YOUR_TOKEN

# Export only your most recent run
nrc2gpx export -t YOUR_TOKEN --latest

# Export your last 5 runs
nrc2gpx export -t YOUR_TOKEN --latest 5

# Export runs from a date range
nrc2gpx export -t YOUR_TOKEN --since 2026-01-01 --until 2026-06-30

# Pick runs from a list
nrc2gpx export -t YOUR_TOKEN --pick

# Export specific activities by ID
nrc2gpx export -t YOUR_TOKEN --id 3f2c... --id 9a1b...
```

Example of `list` / `--pick`:

```
   #  Date               Distance  Duration       Pace  GPS  Name
-----------------------------------------------------------------
   1  2026-11-05 18:12    8.03 km     41:37    5:11/km  yes  Thursday Evening Run
   2  2026-11-03 07:45    5.01 km     26:02    5:12/km  yes  Tuesday Morning Run
   3  2026-11-01 10:20    6.40 km     35:55    5:37/km  no   Treadmill Run

Runs to export (e.g. 1,3,5-8 or 'all'; Enter to cancel): 1-2
```

### Options

| Option | Commands | Description |
| --- | --- | --- |
| `-t`, `--token` | all | Nike bearer token (with or without the `Bearer ` prefix) |
| `--since YYYY-MM-DD` | all | Only runs on or after this date |
| `--until YYYY-MM-DD` | all | Only runs on or before this date |
| `--latest [N]` | `export` | Only the *N* most recent runs with GPS (default 1) |
| `--pick` | `export` | Choose runs interactively from a numbered list |
| `--id ID` | `export` | Export a specific activity (repeatable) |
| `-o`, `--output DIR` | `export` | Output folder (default `nrc_gpx`) |
| `--overwrite` | `export` | Overwrite GPX files that already exist |
| `--raw` | `export` | Also save the raw JSON of each activity |

`--latest`, `--pick` and `--id` are mutually exclusive. `--since`/`--until` can be combined with `--latest` and `--pick`.

### Output

Files are named after the run's local start time, e.g. `2026-11-05_18-12_nrc.gpx`. Each file is a standard GPX 1.1 track with coordinates, timestamps and (if available) elevation.

**Runs without GPS** (treadmill and indoor runs, or runs recorded with location turned off) have no route, so they are skipped.

## Importing into other apps

- **Strava:** *Upload* → *File* → select one or more GPX files (up to 25 at a time)
- **Garmin Connect:** *Import Data* (cloud icon) → drag the files in
- **Komoot, Runalyze, Google Earth, QGIS…:** open or import the GPX directly

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `Nike rejected the token (HTTP 401)` | The token has expired (about 1 hour) or was copied incompletely. Get a fresh one. |
| `Endpoint not found (HTTP 404)` | Nike changed its API. Please [open an issue](../../issues). |
| `'nrc2gpx' is not recognized...` | Use `python -m nrc2gpx ...`, or add pip's Scripts folder to `PATH`. |
| A run is skipped as "no GPS data" | NRC didn't record a route for it (treadmill/indoor). Nothing to export. |

## How it works

NRC2GPX calls two undocumented Nike endpoints with your token:

| Purpose | Endpoint |
| --- | --- |
| List runs (paginated) | `GET https://api.nike.com/plus/v3/activities/before_id/v3/{before_id}?limit=30&types=run,jogging` |
| Run details and metrics | `GET https://api.nike.com/sport/v3/me/activity/{id}?metrics=ALL` |

It joins the `latitude`, `longitude` and `elevation` metric streams into GPX track points. The older list endpoint (`/sport/v3/me/activities/after_time/0`), used by earlier exporters, now returns **404**. That is why those tools stopped working.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## Credits

NRC2GPX stands on the shoulders of people who reverse-engineered the Nike API before me:

- **[niw](https://gist.github.com/niw/858c1ecaef89858893681e46db63db66)**: the original NikePlus API description and fetch script
- **[Yasoob Khalid](https://yasoob.me/posts/nike-run-club-data-visualization/)**: the blog post on extracting NRC data and the original [`nrc-exporter`](https://github.com/yasoob/nrc-exporter), which inspired this tool
- **[Shailendra Bhatt](https://www.shailendrabhatt.com/2020/11/extracting-running-data-out-of-nrcnike.html)**: documented the newer `before_id` list endpoint
- **[tsutsutaku/nike-runclub-mcp](https://github.com/tsutsutaku/nike-runclub-mcp)**: confirmed the current endpoint combination

## Disclaimer

This is an unofficial, personal project. It is **not affiliated with, endorsed by or supported by Nike, Inc.** "Nike" and "Nike Run Club" are trademarks of Nike, Inc. NRC2GPX only accesses your own data, with a token you provide, and stores nothing except the files it writes to your computer. Use it at your own risk; the API it depends on may change without notice.

## License

[MIT](LICENSE) © 2026 Tilen Padovnik
