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
ACTIVITIES_CACHE = Path.home / ".garminworldmap" / "activities_cache.json"
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

def get_client (email, password, MFA):
    token_store_path = str(TOKEN_STORE)
    try:
        client = Garmin
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

    client = Garmin(email, password, prompt_mfa=lambda: input("MFA code: "))
    try:
        client.login(token_store_path)  
    except GarminConnectTooManyRequestsError as e:
        print(f"Rate limited by Garmin: {e}")
        sys.exit(1)

    print(f"Logged in and cached session to {token_store_path}")
    return client

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