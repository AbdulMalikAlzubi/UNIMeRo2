import tkinter as tk
from tkinter import messagebox
import requests
from urllib.parse import quote
import webbrowser

import show_route2  # unser Modul

# ----------------- MAPBOX KONFIGURATION -----------------

# Deinen echten Mapbox-Token einsetzen:
MAPBOX_ACCESS_TOKEN = (
    "pk.eyJ1IjoiYWFsenViaSIsImEiOiJjbWliajF5aGYwM2toMndxemIwYTh4bXNrIn0.riDqdXb-o1KisGpQpXmXbA"
)

DEFAULT_HEADERS = {
    "User-Agent": "MalikRoadProject/1.0"
}

# ----------------- OSRM KONFIGURATION -----------------
# Wenn du einen eigenen OSRM-Server hast, HIER eintragen:
# z.B. "http://localhost:5000" oder deine AWS-/Docker-URL
OSRM_BASE_URL = "http://router.project-osrm.org"
MAX_MATCH_DISTANCE_M = 15.0  # Matching-Radius in Metern (Punkt→Segment)


# ============================================================
# Geocoding-Funktion (Adresse -> lat/lon) über Mapbox
# ============================================================
def geocode_address_to_latlon(address: str):
    encoded_address = quote(address)

    url = (
        f"https://api.mapbox.com/geocoding/v5/mapbox.places/"
        f"{encoded_address}.json?access_token={MAPBOX_ACCESS_TOKEN}&limit=1"
    )
    resp = requests.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("features"):
        raise ValueError(f"Keine Koordinaten für Adresse gefunden: {address}")

    lon, lat = data["features"][0]["center"]
    return lat, lon


# ============================================================
# Routing-Funktion (Start/Ziel-Koordinaten -> Liste von (lat,lon))
#  → OSRM statt Mapbox Directions
# ============================================================
def build_route_coords(start_lat, start_lon, dest_lat, dest_lon):
    """
    Nutzt OSRM Route API.
    Rückgabe: Liste von (lat, lon).
    """
    url = (
        f"{OSRM_BASE_URL}/route/v1/driving/"
        f"{start_lon},{start_lat};{dest_lon},{dest_lat}"
        "?overview=full&geometries=geojson"
    )

    resp = requests.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("routes"):
        raise ValueError("Keine Route von OSRM gefunden.")

    coords = data["routes"][0]["geometry"]["coordinates"]  # [ [lon, lat], ... ]
    route_coords = [(lat, lon) for lon, lat in coords]
    return route_coords


# ============================================================
# TKINTER GUI
# ============================================================
root = tk.Tk()
root.title("Route planen & Kosten berechnen (HTTP + OSRM + Mapbox)")

# ----------------- Eingabefelder -----------------
frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

tk.Label(frame, text="Start-Adresse:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
entry_start = tk.Entry(frame, width=50)
entry_start.grid(row=0, column=1, columnspan=2, padx=5, pady=5)

tk.Label(frame, text="Ziel-Adresse:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
entry_dest = tk.Entry(frame, width=50)
entry_dest.grid(row=1, column=1, columnspan=2, padx=5, pady=5)

# Beispielwerte
entry_start.insert(0, "Fritz-Tarnow-Straße 3-1, 60320 Frankfurt am Main")
entry_dest.insert(0, "Josephskirchstraße 1, 60433 Frankfurt am Main")


# Preise für Straßenzustände
tk.Label(frame, text="Preis pro km (VERY GOOD):").grid(row=2, column=0, sticky="w", padx=5)
entry_price_vg = tk.Entry(frame, width=10)
entry_price_vg.insert(0, "0.40")
entry_price_vg.grid(row=2, column=1, sticky="w")

tk.Label(frame, text="Preis pro km (GOOD):").grid(row=3, column=0, sticky="w", padx=5)
entry_price_g = tk.Entry(frame, width=10)
entry_price_g.insert(0, "0.50")
entry_price_g.grid(row=3, column=1, sticky="w")

tk.Label(frame, text="Preis pro km (FAIR):").grid(row=4, column=0, sticky="w", padx=5)
entry_price_f = tk.Entry(frame, width=10)
entry_price_f.insert(0, "0.70")
entry_price_f.grid(row=4, column=1, sticky="w")

tk.Label(frame, text="Preis pro km (VERY POOR):").grid(row=5, column=0, sticky="w", padx=5)
entry_price_vp = tk.Entry(frame, width=10)
entry_price_vp.insert(0, "0.90")
entry_price_vp.grid(row=5, column=1, sticky="w")

tk.Label(frame, text="Preis pro km (NOT MEASURED):").grid(row=6, column=0, sticky="w", padx=5)
entry_price_nm = tk.Entry(frame, width=10)
entry_price_nm.insert(0, "0.30")
entry_price_nm.grid(row=6, column=1, sticky="w")


# Label für Ergebnis
label_result = tk.Label(root, text="", justify="left", anchor="w")
label_result.pack(padx=10, pady=10, fill="both")


# ------------------------------------------------------------
# Start/Ziel tauschen
# ------------------------------------------------------------
def swap_addresses():
    """Start- und Zieladresse im GUI vertauschen."""
    start = entry_start.get()
    dest = entry_dest.get()

    entry_start.delete(0, tk.END)
    entry_dest.delete(0, tk.END)

    entry_start.insert(0, dest)
    entry_dest.insert(0, start)


# ----------------- Button-Callback -----------------
def on_calculate_route():
    start_addr = entry_start.get().strip()
    dest_addr = entry_dest.get().strip()

    if not start_addr or not dest_addr:
        messagebox.showerror("Fehler", "Bitte Start- und Zieladresse eingeben.")
        return

    # Preise lesen
    try:
        price_per_km = {
            "VERY GOOD": float(entry_price_vg.get().replace(",", ".")),
            "GOOD": float(entry_price_g.get().replace(",", ".")),
            "FAIR": float(entry_price_f.get().replace(",", ".")),
            "VERY POOR": float(entry_price_vp.get().replace(",", ".")),
            "NOT MEASURED": float(entry_price_nm.get().replace(",", ".")),
        }
    except ValueError:
        messagebox.showerror("Fehler", "Bitte gültige Zahlen für die Preise eingeben.")
        return

    # 1) Geocoding
    try:
        start_lat, start_lon = geocode_address_to_latlon(start_addr)
        dest_lat, dest_lon = geocode_address_to_latlon(dest_addr)
    except Exception as e:
        messagebox.showerror("Geocoding-Fehler", str(e))
        return

    # 2) Route berechnen (OSRM)
    try:
        route_coords = build_route_coords(start_lat, start_lon, dest_lat, dest_lon)
    except Exception as e:
        messagebox.showerror("Routing-Fehler", str(e))
        return

    if not route_coords:
        messagebox.showinfo("Info", "Es wurde keine Route gefunden.")
        return

    # 3) Matching + Karte + Kosten + Breakdown
    try:
        total_cost, total_dist_km, breakdown = show_route2.show_route_and_cost(
            route_coords,
            price_per_km,
            max_dist_m=MAX_MATCH_DISTANCE_M,           # Matching-Radius in Metern
            output_html="route_map.html",
        )
    except Exception as e:
        messagebox.showerror("Fehler bei Kosten/Karte", str(e))
        return

    # 4) Rechenweg-Text bauen
    lines = [
        f"Gesamtdistanz: {total_dist_km:.2f} km",
        f"Gesamtkosten: {total_cost:.2f} €",
        "",
        "Aufschlüsselung nach Straßenzustand:",
    ]

    for state, info in breakdown.items():
        if info["dist_km"] <= 0:
            continue
        lines.append(
            f"- {state}: {info['dist_km']:.2f} km * "
            f"{info['price_per_km']:.2f} €/km = {info['cost']:.2f} €"
        )

    text = "\n".join(lines)

    # Im Label anzeigen (kein Extra-Popup mehr)
    label_result.config(text=text)

    # Karte im Browser öffnen
    webbrowser.open("route_map.html")


# ----------------- Buttons -----------------
btn_swap = tk.Button(
    root,
    text="Start/Ziel tauschen",
    command=swap_addresses,
)
btn_swap.pack(padx=5, pady=5)

btn_calc = tk.Button(
    root,
    text="Route planen & Kosten berechnen",
    command=on_calculate_route,
)
btn_calc.pack(padx=5, pady=10)

root.mainloop()
