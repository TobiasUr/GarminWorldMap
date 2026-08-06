# GarminWorldMap

Plot every Garmin Connect activity you've ever recorded onto a single interactive map.

Pulls your full activity history via the [Garmin Connect API](https://github.com/cyberjunky/python-garminconnect), downloads the GPS track for each one, and renders them all as colored routes (or a Strava-style density heatmap) on a zoomable [Leaflet](https://leafletjs.com/) map.

## Quick start (Windows, no Python required)

Download `main.exe` from the [Releases](../../releases) page and run it. On first run it'll ask for your Garmin email and password, then generate `all_activities.html` in the same folder — open that in a browser to view your map.

> Windows may show a SmartScreen warning since the executable isn't code-signed. Click "More info" → "Run anyway" if you trust the source (or just run from source instead — see below).

## Setup (run from source)

```bash
git clone https://github.com/<you>/GarminWorldMap.git
cd GarminWorldMap
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your Garmin Connect credentials:

```bash
cp .env.example .env
```

> Credentials are only used to log in and are never stored in plaintext beyond your local `.env`. After the first successful login, a session token is cached to `~/.garminconnect` so you won't need to log in again for a while.

## Usage

```bash
python garmin_map.py
```

This will:
1. Log in to Garmin Connect (using cached tokens if available)
2. Fetch your full activity list (cached locally in `data/activities_cache.json`)
3. Download the GPX track for every activity that has one (cached in `data/gpx/`)
4. Render everything onto `all_activities.html`

Open `all_activities.html` in a browser to explore the map.

### Options

```bash
python garmin_map.py --heatmap          # render a density heatmap instead of colored routes
python garmin_map.py --refresh          # re-fetch the activity list instead of using the cache
python garmin_map.py --output map.html  # customize the output file name
```

## Notes

- Garmin's API isn't official/public, so it can rate-limit login attempts if hit too often — the token caching is there specifically to avoid that.
- Everything downloaded (activity metadata, GPX files) is cached under `data/` so re-runs are fast and don't re-hit Garmin's servers unnecessarily. This directory is gitignored since it's personal data.
- Routes are colored by sport type (running, cycling, hiking, etc.) — see `SPORT_COLORS` in `garmin_map.py` to customize.

## Disclaimer

This uses an unofficial, reverse-engineered API and is not affiliated with or endorsed by Garmin. Use at your own risk, and don't hammer their servers.

## License

MIT — see [LICENSE](LICENSE).# GarminWorldMap

Plot every Garmin Connect activity you've ever recorded onto a single interactive map.

Pulls your full activity history via the [Garmin Connect API](https://github.com/cyberjunky/python-garminconnect), downloads the GPS track for each one, and renders them all as colored routes (or a Strava-style density heatmap) on a zoomable [Leaflet](https://leafletjs.com/) map.

## Setup

```bash
git clone https://github.com/<you>/GarminWorldMap.git
cd GarminWorldMap
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your Garmin Connect credentials:

```bash
cp .env.example .env
```

> Credentials are only used to log in and are never stored in plaintext beyond your local `.env`. After the first successful login, a session token is cached to `~/.garminconnect` so you won't need to log in again for a while.

## Usage

```bash
python garmin_map.py
```

This will:
1. Log in to Garmin Connect (using cached tokens if available)
2. Fetch your full activity list (cached locally in `data/activities_cache.json`)
3. Download the GPX track for every activity that has one (cached in `data/gpx/`)
4. Render everything onto `all_activities.html`

Open `all_activities.html` in a browser to explore the map.

### Options

```bash
python garmin_map.py --heatmap          # render a density heatmap instead of colored routes
python garmin_map.py --refresh          # re-fetch the activity list instead of using the cache
python garmin_map.py --output map.html  # customize the output file name
```

## Notes

- Garmin's API isn't official/public, so it can rate-limit login attempts if hit too often — the token caching is there specifically to avoid that.
- Everything downloaded (activity metadata, GPX files) is cached under `data/` so re-runs are fast and don't re-hit Garmin's servers unnecessarily. This directory is gitignored since it's personal data.
- Routes are colored by sport type (running, cycling, hiking, etc.) — see `SPORT_COLORS` in `garmin_map.py` to customize.

## Disclaimer

This uses an unofficial, reverse-engineered API and is not affiliated with or endorsed by Garmin. Use at your own risk, and don't hammer their servers.

## License

[MIT](LICENSE).

## Support

If you would like to support this and my other projects, you can <script type="text/javascript" src="https://cdnjs.buymeacoffee.com/1.0.0/button.prod.min.js" data-name="bmc-button" data-slug="tobiasurbanek" data-color="#FFDD00" data-emoji=""  data-font="Cookie" data-text="Buy me a coffee" data-outline-color="#000000" data-font-color="#000000" data-coffee-color="#ffffff" ></script>
