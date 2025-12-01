import tkinter as tk
from tkinter import messagebox
import requests
import csv
from datetime import datetime
from pathlib import Path

# ----------------- MAPBOX KONFIGURATION -----------------

# HIER deinen eigenen Mapbox-Token eintragen!
MAPBOX_ACCESS_TOKEN = "pk.eyJ1IjoiYWFsenViaSIsImEiOiJjbWliajF5aGYwM2toMndxemIwYTh4bXNrIn0.riDqdXb-o1KisGpQpXmXbA"

# Optional: für alle Requests ein gemeinsamer Header
DEFAULT_HEADERS = {
    "User-Agent": "MalikRoadProject/1.0"
}

# ----------------- OSRM KONFIGURATION -----------------

# Öffentlicher OSRM-Server oder dein eigener:
# z.B. "https://router.project-osrm.org" oder "http://localhost:5000"
OSRM_BASE_URL = "https://router.project-osrm.org"

# ----------------- GEOCODING (Adresse -> lat/lon) -----------------

def geocode(address: str):
    """
    Verwendet den Mapbox Geocoding Service,
    um aus einer Adresse (Straße, Hausnr, PLZ, Ort) lat/lon zu holen.
    """
    if not MAPBOX_ACCESS_TOKEN or MAPBOX_ACCESS_TOKEN == "DEIN_MAPBOX_TOKEN_HIER":
        raise RuntimeError("Bitte trage deinen MAPBOX_ACCESS_TOKEN im Code ein.")

    # Adresse für die URL encoden
    search_text = requests.utils.quote(address)

    url = f"https://api.mapbox.com/geocoding/v5/mapbox.places/{search_text}.json"
    params = {
        "access_token": MAPBOX_ACCESS_TOKEN,
        "limit": 1
    }

    response = requests.get(url, params=params, headers=DEFAULT_HEADERS, timeout=10)
    response.raise_for_status()
    data = response.json()

    if "features" not in data or not data["features"]:
        raise ValueError("Adresse wurde nicht gefunden (Mapbox).")

    # Mapbox: center = [lon, lat]
    lon, lat = data["features"][0]["center"]
    return float(lat), float(lon)

# ----------------- ROUTE (Start/Ziel-lat/lon -> OSRM-Punkte) -----------------

def get_route_coords_osrm(start_lat, start_lon, end_lat, end_lon):
    """
    Holt die Fahrstrecke von der OSRM-API (/route)
    und gibt eine Liste von (lat, lon)-Punkten zurück.
    """
    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{end_lon},{end_lat}"
    )
    params = {
        "overview": "full",
        "geometries": "geojson"
    }

    response = requests.get(url, params=params, timeout=15, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    data = response.json()

    if not data.get("routes"):
        raise RuntimeError("Keine Route gefunden (OSRM).")

    coords_lonlat = data["routes"][0]["geometry"]["coordinates"]
    # OSRM liefert [lon, lat] -> umdrehen auf (lat, lon)
    coords_latlon = [(lat, lon) for lon, lat in coords_lonlat]
    return coords_latlon

# ----------------- ROUTE IN CSV SPEICHERN -----------------

def save_route_to_csv(coords):
    """
    Speichert die Routenpunkte in eine CSV-Datei im gleichen Ordner wie das Skript.
    (hier: die OSRM-Route-Punkte)
    """
    base_dir = Path(__file__).resolve().parent
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = base_dir / f"route_{timestamp}.csv"

    with open(filename, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "lat", "lon"])
        for i, (lat, lon) in enumerate(coords):
            writer.writerow([i, lat, lon])

    return filename

# ----------------- TKINTER-GUI -----------------

start_lat = start_lon = None
ziel_lat = ziel_lon = None

def berechne_und_speichere_route():
    global start_lat, start_lon, ziel_lat, ziel_lon

    start_addr = entry_start.get().strip()
    ziel_addr = entry_ziel.get().strip()

    if not start_addr or not ziel_addr:
        messagebox.showerror("Fehler", "Bitte Start- und Zieladresse eingeben.")
        return

    # 1) Adressen geocoden (Mapbox)
    try:
        start_lat, start_lon = geocode(start_addr)
    except Exception as e:
        messagebox.showerror("Fehler bei der Startadresse", str(e))
        return

    try:
        ziel_lat, ziel_lon = geocode(ziel_addr)
    except Exception as e:
        messagebox.showerror("Fehler bei der Zieladresse", str(e))
        return

    # lat/lon untereinander anzeigen
    start_lat_var.set(f"Lat: {start_lat:.6f}")
    start_lon_var.set(f"Lon: {start_lon:.6f}")
    ziel_lat_var.set(f"Lat: {ziel_lat:.6f}")
    ziel_lon_var.set(f"Lon: {ziel_lon:.6f}")

    # 2) Route holen – jetzt über OSRM
    try:
        coords = get_route_coords_osrm(start_lat, start_lon, ziel_lat, ziel_lon)
    except Exception as e:
        messagebox.showerror("Fehler bei der Routenberechnung (OSRM)", str(e))
        return

    # 3) Route in CSV speichern (OSRM-Punkte)
    try:
        csv_path = save_route_to_csv(coords)
    except Exception as e:
        messagebox.showerror("Fehler beim Speichern der Route", str(e))
        return

    info_text = (
        f"Route (OSRM) berechnet.\n"
        f"Anzahl Punkte: {len(coords)}\n\n"
        f"Zwischenspeicher:\n{csv_path}"
    )
    messagebox.showinfo("Fertig", info_text)

    # Debug in Konsole
    print(info_text)

def swap_start_ziel():
    """
    Tauscht die Inhalte der Start- und Ziel-Textfelder
    und leert die angezeigten Koordinaten.
    """
    start_text = entry_start.get()
    ziel_text = entry_ziel.get()

    # Texte in den Entries tauschen
    entry_start.delete(0, tk.END)
    entry_start.insert(0, ziel_text)

    entry_ziel.delete(0, tk.END)
    entry_ziel.insert(0, start_text)

    # Koordinatenanzeige zurücksetzen
    start_lat_var.set("")
    start_lon_var.set("")
    ziel_lat_var.set("")
    ziel_lon_var.set("")

# --------- Fenster aufbauen ---------

root = tk.Tk()
root.title("Fahrtstrecke -> OSRM-Koordinaten + CSV")

frame_input = tk.Frame(root, padx=10, pady=10)
frame_input.pack(fill="x")

# Startadresse
label_start = tk.Label(frame_input, text="Startadresse:")
label_start.grid(row=0, column=0, sticky="w")

entry_start = tk.Entry(frame_input, width=60)
entry_start.grid(row=1, column=0, pady=(0, 10))
entry_start.insert(0, "Fritz-Tarnow-Straße 3-1, 60320 Frankfurt am Main")

# Zieladresse
label_ziel = tk.Label(frame_input, text="Zieladresse:")
label_ziel.grid(row=2, column=0, sticky="w")

entry_ziel = tk.Entry(frame_input, width=60)
entry_ziel.grid(row=3, column=0, pady=(0, 10))
entry_ziel.insert(0, "Josephskirchstraße 1, 60433 Frankfurt am Main")  # Beispiel

button_route = tk.Button(root, text="Route berechnen & speichern",
                         command=berechne_und_speichere_route)
button_route.pack(pady=5)

button_swap = tk.Button(root, text="Start/Ziel tauschen",
                        command=swap_start_ziel)
button_swap.pack(pady=5)

# Ausgabe lat/lon
frame_output = tk.Frame(root, padx=10, pady=10)
frame_output.pack(fill="x")

tk.Label(frame_output, text="Startkoordinaten:").grid(row=0, column=0, sticky="w")
start_lat_var = tk.StringVar()
start_lon_var = tk.StringVar()
tk.Label(frame_output, textvariable=start_lat_var).grid(row=1, column=0, sticky="w")
tk.Label(frame_output, textvariable=start_lon_var).grid(row=2, column=0, sticky="w")

tk.Label(frame_output, text="Zielkoordinaten:").grid(row=3, column=0, sticky="w", pady=(10, 0))
ziel_lat_var = tk.StringVar()
ziel_lon_var = tk.StringVar()
tk.Label(frame_output, textvariable=ziel_lat_var).grid(row=4, column=0, sticky="w")
tk.Label(frame_output, textvariable=ziel_lon_var).grid(row=5, column=0, sticky="w")

root.mainloop()
