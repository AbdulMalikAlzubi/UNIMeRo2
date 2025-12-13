import math
import folium
import os
import requests

# ============================================================
# API-Konfiguration
# ============================================================
API_BASE_URL = os.getenv("API_BASE_URL", "http://100.25.221.124:8000")

STATE_COLORS = {
    "VERY GOOD": "green", "GOOD": "lightgreen", "FAIR": "orange",
    "VERY POOR": "red", "NOT MEASURED": "gray",
}

TRAFFIC_COLORS = {
    "unknown": "gray", "low": "#00FF00", "moderate": "#FFA500",
    "heavy": "#FF0000", "severe": "#8B0000",
}

STATE_PRIORITY = {
    "NOT MEASURED": 0, "VERY GOOD": 1, "GOOD": 2, "FAIR": 3, "VERY POOR": 4,
}

# ============================================================
# Hilfsfunktionen (Geometrie & DB)
# ============================================================
def load_db_points():
    url = f"{API_BASE_URL}/db_points"
    try:
        resp = requests.get(url, timeout=4)
        resp.raise_for_status()
        raw = resp.json()
    except Exception:
        return []

    db_points = []
    for p in raw:
        try:
            lat = float(p.get("lat") or p.get("lat_matched"))
            lon = float(p.get("lon") or p.get("lon_matched"))
            state_raw = p.get("state") or p.get("roughness") or "NOT MEASURED"
            db_points.append({"lat": lat, "lon": lon, "state": str(state_raw).upper()})
        except:
            continue
    return db_points

def choose_worse_state(state1, state2):
    if state1 is None: return state2
    if state2 is None: return state1
    p1 = STATE_PRIORITY.get(state1, 0)
    p2 = STATE_PRIORITY.get(state2, 0)
    return state1 if p1 >= p2 else state2

def latlon_to_xy(lat, lon, lat0):
    R = 6371000.0
    phi = math.radians(lat)
    phi0 = math.radians(lat0)
    lam = math.radians(lon)
    x = R * lam * math.cos(phi0)
    y = R * phi
    return x, y

def point_to_segment_distance_m(lat, lon, lat1, lon1, lat2, lon2, lat0):
    x, y = latlon_to_xy(lat, lon, lat0)
    x1, y1 = latlon_to_xy(lat1, lon1, lat0)
    x2, y2 = latlon_to_xy(lat2, lon2, lat0)
    dx = x2 - x1; dy = y2 - y1
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0: return math.hypot(x - x1, y - y1)
    t = ((x - x1) * dx + (y - y1) * dy) / seg_len2
    t = max(0.0, min(1.0, t))
    projx = x1 + t * dx; projy = y1 + t * dy
    return math.hypot(x - projx, y - projy)

def find_segment_state(lat1, lon1, lat2, lon2, db_points, lat0, max_dist_m):
    best_state = None
    for p in db_points:
        d = point_to_segment_distance_m(p["lat"], p["lon"], lat1, lon1, lat2, lon2, lat0)
        if d <= max_dist_m:
            best_state = choose_worse_state(best_state, p["state"])
    return best_state

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ============================================================
# HAUPTFUNKTION (Robustere Anzeige)
# ============================================================
def show_route_and_cost(routes_data, price_per_km, 
                        traffic_multipliers=None,
                        max_dist_m=50.0,
                        output_html="route_map.html"):
    
    if not routes_data:
        raise ValueError("Keine Routendaten übergeben.")

    if traffic_multipliers is None:
        traffic_multipliers = {"unknown": 1.0}

    db_points = load_db_points()

    # Karte zentrieren
    first_route = routes_data[0]['coords']
    avg_lat = sum(lat for lat, _ in first_route) / len(first_route)
    avg_lon = sum(lon for _, lon in first_route) / len(first_route)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=12)

    results_summary = []

    # --- Schritt 1: Erst alles berechnen, DANN Layer erstellen ---
    # Damit der Name im Menü ("Route 1: 20€") sofort stimmt.
    
    for idx, route_entry in enumerate(routes_data):
        route_coords = route_entry['coords']
        congestion_data = route_entry['congestion']
        
        # --- A. Berechnung ---
        total_cost = 0.0
        total_dist_km = 0.0
        breakdown = {}
        
        # Temporäre Liste für Segmente speichern, damit wir nicht 2x rechnen müssen
        calculated_segments = []

        for i in range(len(route_coords) - 1):
            lat1, lon1 = route_coords[i]
            lat2, lon2 = route_coords[i + 1]

            dist_km = haversine_km(lat1, lon1, lat2, lon2)
            total_dist_km += dist_km

            # Zustand
            segment_state = None
            if db_points:
                segment_state = find_segment_state(lat1, lon1, lat2, lon2, db_points, avg_lat, max_dist_m)
            if not segment_state: segment_state = "NOT MEASURED"

            base_price = price_per_km.get(segment_state, 0.0)

            # Traffic
            traffic_factor = 1.0
            cong_val = "unknown"
            if congestion_data and i < len(congestion_data):
                cong_val = congestion_data[i]
                traffic_factor = traffic_multipliers.get(cong_val, 1.0)
            
            # Kosten
            segment_cost = dist_km * base_price * traffic_factor
            total_cost += segment_cost

            if segment_state not in breakdown: breakdown[segment_state] = {"dist_km": 0.0, "cost": 0.0}
            breakdown[segment_state]["dist_km"] += dist_km
            breakdown[segment_state]["cost"] += segment_cost

            # Daten speichern für Visualisierung gleich
            calculated_segments.append({
                "p1": (lat1, lon1), "p2": (lat2, lon2),
                "state": segment_state, "cong": cong_val,
                "factor": traffic_factor, "cost": segment_cost
            })

        # --- B. Visualisierung (FeatureGroups erstellen) ---
        # Jetzt kennen wir die Gesamtkosten und können den Namen bauen
        
        name_prefix = f"Route {idx+1}"
        label_cond = f"{name_prefix}: Zustand ({total_cost:.2f} € | {total_dist_km:.1f} km)"
        label_traff = f"{name_prefix}: Verkehr"
        
        # Route 1 an, andere aus
        is_visible = (idx == 0)

        fg_condition = folium.FeatureGroup(name=label_cond, show=is_visible)
        fg_traffic = folium.FeatureGroup(name=label_traff, show=is_visible)

        for seg in calculated_segments:
            tooltip_text = (
                f"<b>{name_prefix}</b><br>"
                f"Zustand: {seg['state']}<br>"
                f"Traffic: {seg['cong']} (x{seg['factor']})<br>"
                f"Abschnitt: {seg['cost']:.2f} €"
            )

            # Zustand-Linie (Dicker)
            color_cond = STATE_COLORS.get(seg['state'], "gray")
            folium.PolyLine(
                [seg['p1'], seg['p2']],
                weight=10, color=color_cond, opacity=0.6, tooltip=tooltip_text
            ).add_to(fg_condition)

            # Traffic-Linie (Dünner)
            color_traff = TRAFFIC_COLORS.get(seg['cong'], "gray")
            folium.PolyLine(
                [seg['p1'], seg['p2']],
                weight=4, color=color_traff, opacity=1.0, tooltip=tooltip_text
            ).add_to(fg_traffic)

        fg_condition.add_to(m)
        fg_traffic.add_to(m)

        results_summary.append({
            "name": name_prefix,
            "cost": total_cost,
            "dist": total_dist_km,
            "breakdown": breakdown
        })

    # Start/Ziel Marker
    if routes_data:
        s = routes_data[0]['coords'][0]
        e = routes_data[0]['coords'][-1]
        folium.Marker(s, popup="Start", icon=folium.Icon(color="green", icon="play")).add_to(m)
        folium.Marker(e, popup="Ziel", icon=folium.Icon(color="red", icon="stop")).add_to(m)

    folium.LayerControl(collapsed=False).add_to(m)

    # Legende
    legend_html = """
     <div style="position: fixed; bottom: 30px; left: 30px; width: 220px; z-index:9999; font-size:12px;
        background-color: white; opacity: 0.9; padding: 10px; border: 2px solid grey; border-radius: 5px;">
       <b>Legende & Auswahl</b><br>
       <span style="color:gray; font-size:10px;">Oben rechts Routen umschalten!</span><br><br>
       <b>1. Zustand (Breite Linie)</b><br>
       <i style="background:green;width:10px;height:10px;float:left;margin-right:5px;border-radius:50%"></i> Very Good<br>
       <i style="background:lightgreen;width:10px;height:10px;float:left;margin-right:5px;border-radius:50%"></i> Good<br>
       <i style="background:orange;width:10px;height:10px;float:left;margin-right:5px;border-radius:50%"></i> Fair<br>
       <i style="background:red;width:10px;height:10px;float:left;margin-right:5px;border-radius:50%"></i> Very Poor<br>
       <br>
       <b>2. Verkehr (Innere Linie)</b><br>
       <i style="background:#00FF00;width:10px;height:10px;float:left;margin-right:5px"></i> Flüssig<br>
       <i style="background:#FFA500;width:10px;height:10px;float:left;margin-right:5px"></i> Zäh<br>
       <i style="background:#FF0000;width:10px;height:10px;float:left;margin-right:5px"></i> Stau<br>
       <i style="background:#8B0000;width:10px;height:10px;float:left;margin-right:5px"></i> Massiv<br>
     </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save(output_html)
    return results_summary