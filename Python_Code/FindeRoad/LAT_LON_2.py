import tkinter as tk
from tkinter import messagebox
import requests
import csv
from datetime import datetime
from pathlib import Path

# ----------------- GEOCODING KONFIGURATION (Nominatim / OSM) -----------------
# Wir verwenden Nominatim (OpenStreetMap) als Geocoder, kein Token nötig.
# Bitte den User-Agent ggf. mit Kontaktinfo (E-Mail) ergänzen, um die Nominatim-Richtlinien einzuhalten.
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
    Verwendet den Nominatim Geocoding Service (OpenStreetMap),
    um aus einer Adresse (Straße, Hausnr, PLZ, Ort) lat/lon zu holen.
    Kein Token nötig, aber bitte keine exzessiven Anfragen senden.
    """
    address = address.strip()
    if not address:
        raise ValueError("Leere Adresse.")

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }

    # Nominatim verlangt einen sinnvollen User-Agent
    headers = {
        "User-Agent": DEFAULT_HEADERS.get("User-Agent", "MalikRoadProject/1.0")
    }

    response = requests.get(url, params=params, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    if not data:
        raise ValueError("Adresse wurde nicht gefunden (Nominatim/OSM).")

    lat = float(data[0]["lat"])
    lon = float(data[0]["lon"])
    return lat, lon


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


# ----------------- BUTTON-FUNKTIONEN -----------------

def berechne_und_speichere_route():
    """
    Wird aufgerufen, wenn der Button 'Route berechnen & speichern' geklickt wird.
    Liest Start-/Zieladresse, geokodiert sie mit Nominatim (OSM), holt die Route von OSRM
    und speichert sie als CSV.
    """
    start_addr = entry_start.get().strip()
    ziel_addr = entry_ziel.get().strip()

    if not start_addr or not ziel_addr:
        messagebox.showerror("Fehler", "Bitte Start- und Zieladresse eingeben.")
        return

    # 1) Adressen geocoden (Nominatim / OSM)
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

    # 3) Route in CSV speichern
    try:
        csv_path = save_route_to_csv(coords)
    except Exception as e:
        messagebox.showerror("Fehler beim Speichern der Route", str(e))
        return

    info_text = (
        f"Route berechnet (OSRM).\n"
        f"Punkte: {len(coords)}\n\n"
        f"Gespeichert als:\n{csv_path}"
    )
    messagebox.showinfo("Fertig", info_text)


def swap_start_ziel():
    """
    Tauscht die Start- und Zieladresse.
    """
    s = entry_start.get()
    z = entry_ziel.get()
    entry_start.delete(0, tk.END)
    entry_start.insert(0, z)
    entry_ziel.delete(0, tk.END)
    entry_ziel.insert(0, s)


# ----------------- TKINTER-GUI -----------------

root = tk.Tk()
root.title("Fahrtstrecke -> OSRM-Koordinaten + CSV")

frame_input = tk.Frame(root, padx=10, pady=10)
frame_input.pack(fill="x")

# Startadresse
tk.Label(frame_input, text="Startadresse:").grid(row=0, column=0, sticky="w")
entry_start = tk.Entry(frame_input, width=60)
entry_start.grid(row=1, column=0, sticky="we", pady=(0, 10))

# Beispiel
entry_start.insert(0, "Fritz-Tarnow-Straße 3-1, 60320 Frankfurt am Main")

# Zieladresse
tk.Label(frame_input, text="Zieladresse:").grid(row=2, column=0, sticky="w")
entry_ziel = tk.Entry(frame_input, width=60)
entry_ziel.grid(row=3, column=0, sticky="we", pady=(0, 10))

entry_ziel.insert(0, "Josephskirchstraße 1, 60433 Frankfurt am Main")

# Buttons
button_route = tk.Button(root, text="Route berechnen & speichern",
                         command=berechne_und_speichere_route)
button_route.pack(pady=5)

button_swap = tk.Button(root, text="Start/Ziel tauschen",
                        command=swap_start_ziel)
button_swap.pack(pady=5)

# Ausgabe-Koordinaten
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
