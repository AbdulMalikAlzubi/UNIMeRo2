import tkinter as tk
from tkinter import messagebox
import requests
from urllib.parse import quote
import webbrowser
import os

# Importiert show_route2.py
import show_route2

# ----------------- MAPBOX KONFIGURATION -----------------
MAPBOX_ACCESS_TOKEN = (
    "pk.eyJ1IjoiYWFsenViaSIsImEiOiJjbWliajF5aGYwM2toMndxemIwYTh4bXNrIn0.riDqdXb-o1KisGpQpXmXbA"
)

DEFAULT_HEADERS = {
    "User-Agent": "MalikRoadProject/1.0"
}

MAX_MATCH_DISTANCE_M = 50.0  

# ============================================================
# Geocoding
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
        raise ValueError(f"Keine Koordinaten gefunden für: {address}")

    lon, lat = data["features"][0]["center"]
    return lat, lon

# ============================================================
# Routing
# ============================================================
def build_route_data(waypoints, show_alternatives=False):
    profile = "driving-traffic"
    coordinates_str = ";".join([f"{lon},{lat}" for lat, lon in waypoints])
    
    # Alternativen anfordern
    alternatives_param = "true" if show_alternatives else "false"
    
    print(f"--- Mapbox Anfrage (Alternativen={alternatives_param}) ---")

    url = (
        f"https://api.mapbox.com/directions/v5/mapbox/{profile}/"
        f"{coordinates_str}?geometries=geojson&overview=full&annotations=congestion"
        f"&alternatives={alternatives_param}"
        f"&access_token={MAPBOX_ACCESS_TOKEN}"
    )

    resp = requests.get(url, headers=DEFAULT_HEADERS)
    resp.raise_for_status()
    data = resp.json()

    if not data.get("routes"):
        raise ValueError("Keine Route gefunden.")

    all_routes_output = []

    for r_idx, route in enumerate(data["routes"]):
        coords_raw = route["geometry"]["coordinates"]
        route_coords = [(lat, lon) for lon, lat in coords_raw]

        route_congestion = []
        if "legs" in route:
            for leg in route["legs"]:
                if "annotation" in leg and "congestion" in leg["annotation"]:
                    route_congestion.extend(leg["annotation"]["congestion"])
        
        all_routes_output.append({
            "coords": route_coords,
            "congestion": route_congestion
        })
        print(f"  -> Route {r_idx+1}: {len(route_coords)} Koordinaten")

    return all_routes_output

# ============================================================
# GUI
# ============================================================
root = tk.Tk()
root.title("IRI Projekt: Routenplaner Ultimate")

main_frame = tk.Frame(root)
main_frame.pack(padx=10, pady=10, fill="both", expand=True)

# Adressen
tk.Label(main_frame, text="Routenplanung:", font=("Arial", 10, "bold")).pack(anchor="w", pady=(0, 5))
address_container = tk.Frame(main_frame)
address_container.pack(fill="x")
entry_widgets = []

def add_address_field(default_text=""):
    row_frame = tk.Frame(address_container)
    row_frame.pack(fill="x", pady=2)
    idx = len(entry_widgets) + 1
    tk.Label(row_frame, text=f"Wegpunkt {idx}:", width=12, anchor="w").pack(side="left")
    entry = tk.Entry(row_frame, width=50)
    entry.pack(side="left", fill="x", expand=True, padx=5)
    if default_text: entry.insert(0, default_text)
    entry_widgets.append(entry)

add_address_field("Fritz-Tarnow-Straße 3-1, 60320 Frankfurt am Main")
add_address_field("Josephskirchstraße 1, 60433 Frankfurt am Main")

# Buttons
def on_add_stop(): add_address_field()
def on_swap_addresses():
    if len(entry_widgets) < 2: return
    f, l = entry_widgets[0], entry_widgets[-1]
    t1, t2 = f.get(), l.get()
    f.delete(0, tk.END); f.insert(0, t2)
    l.delete(0, tk.END); l.insert(0, t1)

buttons_frame = tk.Frame(main_frame)
buttons_frame.pack(anchor="w", pady=5)
tk.Button(buttons_frame, text="+ Ziel", command=on_add_stop).pack(side="left", padx=(0, 10))
tk.Button(buttons_frame, text="⇅ Tauschen", command=on_swap_addresses, bg="#DDDDDD").pack(side="left", padx=(0,20))

var_alternatives = tk.BooleanVar(value=False)
chk_alt = tk.Checkbutton(buttons_frame, text="Alternativrouten suchen", variable=var_alternatives)
chk_alt.pack(side="left")

# Settings
settings_frame = tk.Frame(main_frame)
settings_frame.pack(pady=10, anchor="w", fill="x")

tk.Label(settings_frame, text="1. Preis (€/km):", font=("Arial", 9, "bold")).grid(row=0, column=0, sticky="w")
entries_price = {}
labels_p = ["VERY GOOD", "GOOD", "FAIR", "VERY POOR", "NOT MEASURED"]
defaults_p = ["0.40", "0.50", "0.70", "0.90", "0.30"]
for i, (lbl, val) in enumerate(zip(labels_p, defaults_p)):
    tk.Label(settings_frame, text=lbl).grid(row=i+1, column=0, sticky="w", padx=(0,5))
    e = tk.Entry(settings_frame, width=6)
    e.insert(0, val)
    e.grid(row=i+1, column=1, sticky="w")
    entries_price[lbl] = e

tk.Label(settings_frame, text="       ").grid(row=0, column=2)

tk.Label(settings_frame, text="2. Verkehrsfaktor:", font=("Arial", 9, "bold")).grid(row=0, column=3, sticky="w")
entries_traffic = {}
traffic_map = [("low", "Flüssig", "1.0"), ("moderate", "Zäh", "1.2"), ("heavy", "Stau", "1.5"), ("severe", "Massiv", "2.0")]
for i, (key, lbl, val) in enumerate(traffic_map):
    tk.Label(settings_frame, text=lbl).grid(row=i+1, column=3, sticky="w", padx=(10,5))
    e = tk.Entry(settings_frame, width=6)
    e.insert(0, val)
    e.grid(row=i+1, column=4, sticky="w")
    entries_traffic[key] = e

# Execution
label_result = tk.Label(root, text="Bereit...", justify="left", anchor="w", bg="#f0f0f0", relief="sunken", padx=5, pady=5)
label_result.pack(padx=10, pady=10, fill="x")

def on_calculate_route():
    addresses = [e.get().strip() for e in entry_widgets if e.get().strip()]
    if len(addresses) < 2:
        messagebox.showerror("Fehler", "Mindestens 2 Adressen nötig.")
        return

    try:
        price_per_km = {k: float(v.get().replace(",", ".")) for k, v in entries_price.items()}
        traffic_multipliers = {"unknown": 1.0}
        for k, entry in entries_traffic.items():
            traffic_multipliers[k] = float(entry.get().replace(",", "."))
    except ValueError:
        messagebox.showerror("Fehler", "Zahlen prüfen.")
        return

    label_result.config(text="Geocoding...")
    root.update()

    try:
        waypoints = [geocode_address_to_latlon(a) for a in addresses]
        label_result.config(text="Suche Routen...")
        root.update()

        routes_data = build_route_data(waypoints, show_alternatives=var_alternatives.get())
        
        # Info-Text, falls keine Alternativen gefunden wurden
        count = len(routes_data)
        info_txt = f"{count} Route(n) gefunden."
        if count == 1 and var_alternatives.get():
            info_txt += " (Keine sinnvollen Alternativen verfügbar)"
        
        label_result.config(text=f"{info_txt} Berechne Kosten...")
        root.update()

        results = show_route2.show_route_and_cost(
            routes_data,
            price_per_km,
            traffic_multipliers=traffic_multipliers,
            max_dist_m=MAX_MATCH_DISTANCE_M,
            output_html="route_map.html"
        )
        
        lines = [info_txt]
        for res in results:
            lines.append(f"--- {res['name']} ---")
            lines.append(f"Dist: {res['dist']:.2f}km | Kosten: {res['cost']:.2f}€")
        
        label_result.config(text="\n".join(lines))
        webbrowser.open("route_map.html")

    except Exception as e:
        label_result.config(text="Fehler.")
        messagebox.showerror("Fehler", str(e))

btn_calc = tk.Button(root, text="Route berechnen", command=on_calculate_route, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"))
btn_calc.pack(pady=10, fill="x", padx=20)

root.mainloop()