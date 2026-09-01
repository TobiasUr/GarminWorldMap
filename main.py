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
import customtkinter as ctk
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
CREDENTIALS_FILE = Path.home() / ".garminworldmap" / "credentials.json"
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

    mfa_code = (mfa or "").strip()

    def prompt_mfa():
        if mfa_code:
            return mfa_code
        return input("MFA code: ").strip()

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

    client = Garmin(email, password, prompt_mfa=prompt_mfa)
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



#---------------------------------Terminal Output Redirector---------------------------------

class TerminalOutputRedirector:
    def __init__(self, root, text_widget):
        """Initializes the redirector with a target text widget."""
        self.root = root
        self.text_widget = text_widget

    def write(self, string):
        """Intercepts stream writes and inserts them into the widget."""
        def append_to_widget():
            if not self.text_widget.winfo_exists():
                return

            self.text_widget.configure(state="normal")
            self.text_widget.insert(tkinter.END, string)
            self.text_widget.see(tkinter.END)
            self.text_widget.configure(state="disabled")

        self.root.after(0, append_to_widget)

    def flush(self):
        """Required for stream compatibility, keeps buffer operations safe."""
        pass


#---------------------------------Main---------------------------------

def load_saved_credentials():
    try:
        if not CREDENTIALS_FILE.exists():
            return "", ""
        with open(CREDENTIALS_FILE, "r") as f:
            data = json.load(f)
        return str(data.get("email", "")), str(data.get("password", ""))
    except Exception:
        return "", ""


def save_credentials(email, password):
    try:
        CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CREDENTIALS_FILE, "w") as f:
            json.dump({"email": email, "password": password}, f)
    except Exception as exc:
        print(f"Could not save credentials: {exc}")


def run_export(email, password, mfa_code, mode):
    try:
        save_credentials(email, password)
        client = get_client(email=email, password=password, mfa=mfa_code)
        activities = fetch_activities(client)
        download_gpx(client, activities)
        m = build_map(activities, mode=mode)
        m.save(str(OUTPUT_MAP))
        webbrowser.open(str(OUTPUT_MAP.resolve()))
        print(f"\nDone! Open {OUTPUT_MAP.resolve()} in your browser.")
    except Exception as exc:
        print(f"\nError: {exc}")
    finally:
        root.after(0, lambda: button_run.configure(state="normal"))


def clear_cache():
    try:
        if TOKEN_STORE.exists():
            TOKEN_STORE.unlink()
        if ACTIVITIES_CACHE.exists():
            ACTIVITIES_CACHE.unlink()
        if CREDENTIALS_FILE.exists():
            CREDENTIALS_FILE.unlink()
        if GPX_DIR.exists():
            for file in GPX_DIR.glob("*"):
                if file.is_file():
                    file.unlink()
            if not any(GPX_DIR.iterdir()):
                GPX_DIR.rmdir()
        if OUTPUT_MAP.exists():
            OUTPUT_MAP.unlink()
        print("All cached Garmin data has been cleared.")
        eUsername.delete(0, tkinter.END)
        ePassword.delete(0, tkinter.END)
        eMFA.delete(0, tkinter.END)
    except Exception as exc:
        print(f"Could not clear cache: {exc}")


def OK():
    email = eUsername.get().strip()
    password = ePassword.get().strip()
    mfa_code = eMFA.get().strip()
    mode = "heatmap" if heatmap_var.get() else "lines"

    if not email or not password:
        print("Please enter your Garmin email and password.")
        return

    button_run.configure(state="disabled")
    thread = threading.Thread(target=run_export, args=(email, password, mfa_code, mode), daemon=True)
    thread.start()

#---------------------------------GUI---------------------------------
root = ctk.CTk()
root.title("Garmin World Map")
root.geometry("430x620")
ctk.set_appearance_mode("System")
ctk.set_default_color_theme("dark-blue")

main_frame = ctk.CTkFrame(root, corner_radius=12)
main_frame.pack(padx=10, pady=10, fill="x")

saved_email, saved_password = load_saved_credentials()

ctk.CTkLabel(main_frame, text="Garmin World Map", font=("Helvetica", 16, "bold")).pack(pady=(0, 10))
ctk.CTkLabel(main_frame, text="Username:").pack(anchor="w")
eUsername = ctk.CTkEntry(main_frame, width=30)
eUsername.insert(0, saved_email)
eUsername.pack(pady=(0, 5), fill="x")
ctk.CTkLabel(main_frame, text="Password:").pack(anchor="w")
ePassword = ctk.CTkEntry(main_frame, width=30, show="*")
ePassword.insert(0, saved_password)
ePassword.pack(pady=(0, 5), fill="x")
ctk.CTkLabel(main_frame, text="MFA code (optional):").pack(anchor="w")
eMFA = ctk.CTkEntry(main_frame, width=30)
eMFA.pack(pady=(0, 5), fill="x")
heatmap_var = ctk.BooleanVar(value=False)
heatmap_checkbox = ctk.CTkCheckBox(main_frame, text="Heatmap mode", variable=heatmap_var)
heatmap_checkbox.pack(anchor="w", pady=(0, 10))
button_run = ctk.CTkButton(main_frame, text="OK", command=OK, fg_color="#3a7ebf")
button_run.pack(fill="x", pady=(0, 5))
button_clear_cache = ctk.CTkButton(main_frame, text="Clear all cache", command=clear_cache, fg_color="#5a5a5a")
button_clear_cache.pack(fill="x")

ePassword.bind('<Return>', lambda event: OK())
eMFA.bind('<Return>', lambda event: OK())

console_box = ctk.CTkTextbox(root, wrap="word", state="disabled", height=12, fg_color="#1e1e1e", text_color="#f5f5f5")
console_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

# Redirect terminal stdout to our custom class
sys.stdout = TerminalOutputRedirector(root, console_box)

root.mainloop()