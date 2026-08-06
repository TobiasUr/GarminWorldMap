#!/usr/bin/env python3
"""
garmin_map.py

Fetches all Garmin Connect activities, downloads GPX tracks for the ones
that have GPS data, and plots them all on a single interactive map.

Usage:
    python garmin_map.py

First run will prompt for your Garmin email/password (or set env vars
GARMIN_EMAIL / GARMIN_PASSWORD). After that, the session token is cached
locally so you won't need to log in again for a while.

Output:
    gpx/                -> cached GPX files, one per activity
    activities_cache.json -> cached activity metadata (so re-runs are fast)
    all_activities.html -> the final interactive map
"""

import os
import sys
import json
import time
import glob
import getpass
from pathlib import Path

import gpxpy
import folium
from folium.plugins import HeatMap
from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

# ----------------------------------Config-----------------------------------------

TOKEN_STORE = Path.home() / ".garminconnect"
GPX_DIR = Path("gpx")
ACTIVITIES_CACHE = Path("activities_cache.json")
OUTPUT_MAP = Path("all_activities.html")

BATCH_SIZE = 100
REQUEST_DELAY = 0.4  # seconds between API calls, be polite to Garmin's servers

# Color by sport type (falls back to gray for anything not listed)
SPORT_COLORS = {
    "running": "crimson",
    "cycling": "royalblue",
    "hiking": "seagreen",
    "walking": "orange",
    "trail_running": "darkorange",
    "mountain_biking": "purple",
    "swimming": "teal",
}
DEFAULT_COLOR = "gray"


# ----------------------------------Auth-----------------------------------------


def get_client():
    """
    Log in to Garmin Connect, reusing a cached session token if available.

    The library saves/restores tokens itself when you pass a tokenstore path
    into login() — there's no separate "dump" step to call manually.
    """
    tokenstore_path = str(TOKEN_STORE)

    # 1) Try to restore a cached session first — avoids hitting the login
    #    endpoint (and its rate limiting) on every run.
    try:
        client = Garmin()
        client.login(tokenstore_path)
        print("Logged in using cached session token.")
        return client
    except GarminConnectTooManyRequestsError as e:
        print(f"Rate limited by Garmin: {e}")
        print("Wait a while before retrying.")
        sys.exit(1)
    except (
        FileNotFoundError,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
    ) as e:
        print(f"No usable cached session ({e}), logging in fresh...")

    # 2) Fresh login with credentials
    email = os.environ.get("GARMIN_EMAIL") or input("Garmin email: ")
    password = os.environ.get("GARMIN_PASSWORD") or getpass.getpass("Garmin password: ")

    client = Garmin(email=email, password=password)
    try:
        # Passing tokenstore_path here makes login() save the session there
        # after a successful login, so next run can skip straight to step 1.
        client.login(tokenstore_path)
    except GarminConnectTooManyRequestsError as e:
        print(f"Rate limited by Garmin: {e}")
        sys.exit(1)

    print(f"Logged in and cached session to {tokenstore_path}")
    return client


# ----------------------------------Fetching activities-----------------------------------------

def fetch_all_activities(client):
    """Page through Garmin's activity list, with local caching."""
    if ACTIVITIES_CACHE.exists():
        print(f"Loading cached activity list from {ACTIVITIES_CACHE}...")
        with open(ACTIVITIES_CACHE) as f:
            return json.load(f)

    all_activities = []
    start = 0

    while True:
        try:
            batch = client.get_activities(start, BATCH_SIZE)
        except Exception as e:
            print(f"Error fetching activities at offset {start}: {e}")
            print("Stopping here; you can re-run to retry (cache will resume).")
            break

        if not batch:
            break

        all_activities.extend(batch)
        start += BATCH_SIZE
        print(f"Fetched {len(all_activities)} activities so far...")

        if len(batch) < BATCH_SIZE:
            break

        time.sleep(REQUEST_DELAY)

    with open(ACTIVITIES_CACHE, "w") as f:
        json.dump(all_activities, f)
    print(f"Saved {len(all_activities)} activities to {ACTIVITIES_CACHE}")

    return all_activities


def has_gps(activity):
    return activity.get("hasPolyline") is True


# ----------------------------------Downloading GPX tracks-----------------------------------------

def download_gpx_files(client, activities):
    GPX_DIR.mkdir(exist_ok=True)
    gps_activities = [a for a in activities if has_gps(a)]
    print(f"{len(gps_activities)} of {len(activities)} activities have GPS tracks.")

    for i, activity in enumerate(gps_activities, 1):
        activity_id = activity["activityId"]
        gpx_path = GPX_DIR / f"{activity_id}.gpx"

        if gpx_path.exists():
            continue  # already downloaded

        try:
            gpx_data = client.download_activity(
                activity_id,
                dl_fmt=client.ActivityDownloadFormat.GPX,
            )
            if gpx_data and len(gpx_data) > 200:
                with open(gpx_path, "wb") as f:
                    f.write(gpx_data)
            else:
                print(f"  [{i}/{len(gps_activities)}] {activity_id}: empty GPX, skipping")
        except Exception as e:
            print(f"  [{i}/{len(gps_activities)}] {activity_id}: failed ({e})")

        if i % 25 == 0:
            print(f"  Downloaded {i}/{len(gps_activities)}...")

        time.sleep(REQUEST_DELAY)

    print("GPX download complete.")


# ----------------------------------Parsing GPX-----------------------------------------

def get_coords(gpx_path):
    try:
        with open(gpx_path) as f:
            gpx = gpxpy.parse(f)
    except Exception as e:
        print(f"  Could not parse {gpx_path}: {e}")
        return []

    coords = []
    for track in gpx.tracks:
        for segment in track.segments:
            coords.extend([(p.latitude, p.longitude) for p in segment.points])
    return coords


# ----------------------------------Plotting-----------------------------------------

def build_map(activities, mode="lines"):
    """mode: 'lines' for colored routes, 'heatmap' for a Strava-style heatmap."""
    activity_by_id = {a["activityId"]: a for a in activities}

    m = folium.Map(location=[0, 0], zoom_start=2, tiles="cartodbpositron")

    all_lats, all_lons = [], []
    all_points_for_heatmap = []
    plotted = 0

    for gpx_file in sorted(glob.glob(str(GPX_DIR / "*.gpx"))):
        activity_id = int(Path(gpx_file).stem)
        coords = get_coords(gpx_file)
        if not coords:
            continue

        if mode == "heatmap":
            all_points_for_heatmap.extend(coords)
        else:
            activity = activity_by_id.get(activity_id, {})
            sport = activity.get("activityType", {}).get("typeKey", "")
            color = SPORT_COLORS.get(sport, DEFAULT_COLOR)
            name = activity.get("activityName", str(activity_id))

            folium.PolyLine(
                coords,
                color=color,
                weight=2,
                opacity=0.6,
                tooltip=name,
            ).add_to(m)

        all_lats.extend(c[0] for c in coords)
        all_lons.extend(c[1] for c in coords)
        plotted += 1

    if mode == "heatmap" and all_points_for_heatmap:
        HeatMap(all_points_for_heatmap, radius=4, blur=3).add_to(m)

    if all_lats:
        m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])

    print(f"Plotted {plotted} activities on the map.")
    return m


# ----------------------------------Main-----------------------------------------

def main():
    mode = "heatmap" if "--heatmap" in sys.argv else "lines"

    client = get_client()
    activities = fetch_all_activities(client)
    download_gpx_files(client, activities)
    m = build_map(activities, mode=mode)
    m.save(str(OUTPUT_MAP))
    print(f"\nDone! Open {OUTPUT_MAP.resolve()} in your browser.")


if __name__ == "__main__":
    main()