#---------------------------------Import---------------------------------
import os
import sys
import json
import time
import glob
import getpass
import threading
from pathlib import Path
import tkinter
import webbrowser

import gpxpy
import folium
from folium.plugins import HeatMap
from garminconnect import (
    Garmin,
    GarminConnectConnectionError,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
)

#---------------------------------Config files---------------------------------
TOKEN_STORE = Path.home() / ".garminworldmap" / "token"
GPX_DIR = Path.home() / ".garminworldmap" / "gpx"
ACTIVITIES_CACHE = Path.home() / ".garminworldmap" / "activities_cache.json"
OUTPUT_MAP = Path("all_activities.html")

BATCH_SIZE = 100
REQUEST_DELAY = 0.4

SPORT_COLOURS = {
    "running": "crimson",
    "cycling": "royalblue",
    "hiking": "seagreen",
    "walking": "orange",
    "trail_running": "darkorange",
    "mountain_biking": "purple",
    "swimming": "teal",
}

DEFAULT_COLOUR = "gray"

#---------------------------------Authentication---------------------------------

def get_client(email=None, password=None, mfa=None):
    token_store_path = str(TOKEN_STORE)

    if email is None:
        email = input("Garmin email: ").strip()
    if password is None:
        password = getpass.getpass("Garmin password: ")

    try:
        client = Garmin(email, password)
        client.login(token_store_path)
        return client
    except GarminConnectTooManyRequestsError:
        print("Too many requests. Please try again later.")
        sys.exit(1)
    except (
        FileNotFoundError,
        GarminConnectAuthenticationError,
        GarminConnectConnectionError,
    ) as e:
        print(f"No usable cached session ({e}), logging in fresh...")

    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: ").strip())
    try:
        client.login(token_store_path)
    except GarminConnectTooManyRequestsError as e:
        print(f"Rate limited by Garmin: {e}")
        sys.exit(1)

    print(f"Logged in and cached session to {token_store_path}")
    return client

#---------------------------------Fetching activities---------------------------------
def fetch_activities(client):
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
    print(f"Saved {len(all_activities)} activities to cache at {ACTIVITIES_CACHE}")

    return all_activities

def has_GPS(activity):
    return activity.get("hasPolyline") is True

#---------------------------------Download GPX---------------------------------

def download_gpx(client, activities):
    GPX_DIR.mkdir(exist_ok=True)
    gps_activities = [a for a in activities if has_GPS(a)]
    print(f"{len(gps_activities)} of {len(activities)} activities have GPS tracks.")

    for i, activity in enumerate(gps_activities, 1):
        activity_id = activity["activityId"]
        gpx_path = GPX_DIR / f"{activity_id}.gpx"

        if gpx_path.exists():
            print(f"[{i}/{len(gps_activities)}] Skipping {activity_id} (already downloaded).")
            continue
        try:
            gpx_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.GPX)
            if gpx_data and len(gpx_data) > 200:
                if gpx_data and len(gpx_data) > 200:
                    with open(gpx_path, "wb") as f:
                        f.write(gpx_data)
                    print(f"[{i}/{len(gps_activities)}] Downloaded {activity_id} to {gpx_path}.")
                else:
                    print(f"  [{i}/{len(gps_activities)}] {activity_id}: empty GPX, skipping")

        except Exception as e:
            print(f"  [{i}/{len(gps_activities)}] {activity_id}: error downloading GPX: {e}")

        if i % 25 == 0:
            print(f"  Downloaded {i} of {len(gps_activities)} activities so far...")
        time.sleep(REQUEST_DELAY)

    print (f"Downloaded GPX files for {len(gps_activities)} activities to {GPX_DIR}.")

#---------------------------------GPX parsing---------------------------------

def get_coordinates(gpx_path):
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


#---------------------------------Plotting---------------------------------

def build_map(activities, mode='lines'):
    """mode: 'lines' for colored routes, 'heatmap' for a Strava-style heatmap."""
    activity_by_id = {a["activityId"]: a for a in activities}
    m = folium.Map(location=[0, 0], zoom_start=2, tiles="cartodbpositron")

    all_latitudes, all_longitudes = [], []
    all_points_heatmap = []
    plotted = 0

    for gpx_file in sorted(glob.glob(str(GPX_DIR / "*.gpx"))):
        activity_id = int(Path(gpx_file).stem)
        coords = get_coordinates(gpx_file)
        if not coords:
            print(f"  No coordinates found in {gpx_file}, skipping.")
            continue
        if mode == 'heatmap':
            all_points_heatmap.extend(coords)
        else:
            activity = activity_by_id.get(activity_id, {})
            activity_type = activity.get("activityType", {})
            sport = activity_type.get("typeKey", "") if isinstance(activity_type, dict) else ""
            color = SPORT_COLOURS.get(sport, DEFAULT_COLOUR)
            name = activity.get("activityName", str(activity_id))

            folium.PolyLine(coords, color=color, weight=2, opacity=0.6, tooltip=name).add_to(m)

        all_latitudes.extend(c[0] for c in coords)
        all_longitudes.extend(c[1] for c in coords)
        plotted += 1

    if mode == 'heatmap':
        HeatMap(all_points_heatmap, radius=5, blur=3).add_to(m)

    if all_latitudes:
        m.fit_bounds([[min(all_latitudes), min(all_longitudes)], [max(all_latitudes), max(all_longitudes)]])

    print(f"Plotted {plotted} activities on the map.")

    return m




def main():
    mode = "heatmap" if "--heatmap" in sys.argv else "lines"

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")
    client = get_client(email=email, password=password)
    activities = fetch_activities(client)
    download_gpx(client, activities)
    m = build_map(activities, mode=mode)
    m.save(str(OUTPUT_MAP))
    webbrowser.open(str(OUTPUT_MAP.resolve()))
    print(f"\nDone! Open {OUTPUT_MAP.resolve()} in your browser.")


if __name__ == "__main__":
    main()