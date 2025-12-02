import math
import folium
import psycopg2
from psycopg2 import OperationalError

# ============================================================
# DB-Konfiguration
# ============================================================
DB_CONFIG = {
    "host": "roadquality-db.ce9gmcmsmoc6.us-east-1.rds.amazonaws.com",
    "port": 5432,
    "dbname": "postgres",
    "user": "UAS",
    "password": "UAS2025!",
    "sslmode": "require",
}

# Koordinatenspalten in track_point (DB)
LAT_COLUMN = "lat_matched"
LON_COLUMN = "lon_matched"

# Zustand -> Farbe
STATE_COLORS = {
    "VERY GOOD": "green",
    "GOOD": "lightgreen",
    "FAIR": "orange",
    "VERY POOR": "red",
    "NOT MEASURED": "gray",
}

# „Schlechtere“ Zustände höher priorisieren
STATE_PRIORITY = {
    "NOT MEASURED": 0,
    "VERY GOOD": 1,
    "GOOD": 2,
    "FAIR": 3,
    "VERY POOR": 4,
}


# ============================================================
# DB-Punkte laden
# ============================================================
def load_db_points():
    """
    Holt alle (lat, lon, roughness) aus track_point
    und gibt eine Liste von Dicts zurück.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except OperationalError as e:
        raise RuntimeError(
            "Konnte nicht auf die Datenbank zugreifen. "
            "Bitte Verbindung/DB-Konfiguration prüfen."
        ) from e

    cur = conn.cursor()

    sql = f"""
        SELECT {LAT_COLUMN}, {LON_COLUMN}, roughness
        FROM track_point
        WHERE {LAT_COLUMN} IS NOT NULL
          AND {LON_COLUMN} IS NOT NULL
          AND roughness IS NOT NULL;
    """
    cur.execute(sql)

    db_points = []
    for lat, lon, roughness in cur.fetchall():
        db_points.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "state": str(roughness).upper(),   # z.B. "VERY GOOD"
            }
        )

    cur.close()
    conn.close()

    return db_points


def choose_worse_state(state1, state2):
    """Gibt den „schlechteren“ der beiden Zustände zurück."""
    if state1 is None:
        return state2
    if state2 is None:
        return state1
    p1 = STATE_PRIORITY.get(state1, 0)
    p2 = STATE_PRIORITY.get(state2, 0)
    return state1 if p1 >= p2 else state2


# ============================================================
# Geometrie-Helfer: Punkt → Segment (in Metern)
# ============================================================
def latlon_to_xy(lat, lon, lat0):
    """
    Wandelt (lat, lon) grob in Meter-Koordinaten (x, y) um,
    relativ zu einer Referenzbreite lat0.
    """
    R = 6371000.0  # Erdradius in m
    phi = math.radians(lat)
    phi0 = math.radians(lat0)
    lam = math.radians(lon)

    x = R * lam * math.cos(phi0)
    y = R * phi
    return x, y


def point_to_segment_distance_m(lat, lon, lat1, lon1, lat2, lon2, lat0):
    """
    Minimaler Abstand eines Punktes (lat, lon)
    zu einem Segment zwischen (lat1, lon1) und (lat2, lon2), in Metern.
    """
    x, y = latlon_to_xy(lat, lon, lat0)
    x1, y1 = latlon_to_xy(lat1, lon1, lat0)
    x2, y2 = latlon_to_xy(lat2, lon2, lat0)

    dx = x2 - x1
    dy = y2 - y1
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        # Segment ist ein Punkt
        return math.hypot(x - x1, y - y1)

    t = ((x - x1) * dx + (y - y1) * dy) / seg_len2
    t = max(0.0, min(1.0, t))
    projx = x1 + t * dx
    projy = y1 + t * dy

    return math.hypot(x - projx, y - projy)


def find_segment_state(lat1, lon1, lat2, lon2, db_points, lat0, max_dist_m):
    """
    Sucht alle DB-Punkte, die in der Nähe dieses Segments liegen,
    und gibt den „schlechtesten“ gefundenen Zustand zurück.
    """
    best_state = None

    for p in db_points:
        d = point_to_segment_distance_m(
            p["lat"], p["lon"], lat1, lon1, lat2, lon2, lat0
        )
        if d <= max_dist_m:
            best_state = choose_worse_state(best_state, p["state"])

    return best_state


# ============================================================
# Haversine-Distanz in km (für Segmentlängen)
# ============================================================
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0  # Erdradius km
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


# ============================================================
# Hauptfunktion: Karte + Kosten + Breakdown
# ============================================================
def show_route_and_cost(route_coords, price_per_km, max_dist_m=15.0,
                        output_html="route_map.html"):
    """
    route_coords: Liste von (lat, lon) für die geplante Route
    price_per_km: Dict mit Preisen pro km, z.B.:
        {
          "VERY GOOD": 0.40,
          "GOOD": 0.50,
          "FAIR": 0.70,
          "VERY POOR": 0.90,
          "NOT MEASURED": 0.30
        }
    max_dist_m: maximaler Abstand Punkt→Segment, damit DB-Punkt zu Segment gehört

    Rückgabe:
        total_cost (float),
        total_dist_km (float),
        breakdown (dict):
            {
              "VERY GOOD": {"dist_km": ..., "price_per_km": ..., "cost": ...},
              ...
            }
    """
    if not route_coords:
        raise ValueError("Keine Route übergeben.")

    # DB-Punkte (RoadLab/OSRM) laden
    db_points = load_db_points()
    if not db_points:
        # keine DB-Daten -> trotzdem Distanz berechnen, aber alles NOT MEASURED
        pass

    # Karte zentrieren
    avg_lat = sum(lat for lat, _ in route_coords) / len(route_coords)
    avg_lon = sum(lon for _, lon in route_coords) / len(route_coords)

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)

    # Basisroute in hellgrau
    folium.PolyLine(
        route_coords,
        tooltip="Route",
        weight=3,
        color="lightgray",
    ).add_to(m)

    total_cost = 0.0
    total_dist_km = 0.0
    segments_colored = 0

    # Breakdown nach Zustand
    breakdown = {}  # state -> {"dist_km": ..., "price_per_km": ..., "cost": ...}

    # Segment für Segment: Zustand + Kosten
    for i in range(len(route_coords) - 1):
        lat1, lon1 = route_coords[i]
        lat2, lon2 = route_coords[i + 1]

        # Distanz des Segments
        dist_km = haversine_km(lat1, lon1, lat2, lon2)
        total_dist_km += dist_km

        # Zustand aus DB-Punkten in Segmentnähe
        segment_state = None
        if db_points:
            segment_state = find_segment_state(lat1, lon1, lat2, lon2,
                                               db_points, avg_lat, max_dist_m)

        if not segment_state:
            segment_state = "NOT MEASURED"

        # Preis + Kosten
        price = price_per_km.get(segment_state, 0.0)
        segment_cost = dist_km * price
        total_cost += segment_cost

        # Breakdown aktualisieren
        if segment_state not in breakdown:
            breakdown[segment_state] = {
                "dist_km": 0.0,
                "price_per_km": price,
                "cost": 0.0,
            }
        breakdown[segment_state]["dist_km"] += dist_km
        breakdown[segment_state]["cost"] += segment_cost

        # Farbige Linie für das Segment
        color = STATE_COLORS.get(segment_state, "gray")

        folium.PolyLine(
            [(lat1, lon1), (lat2, lon2)],
            weight=6,
            color=color,
            tooltip=f"{segment_state} | {dist_km:.3f} km | {segment_cost:.2f} €",
        ).add_to(m)
        segments_colored += 1

    # Start / Ziel markieren
    start_lat, start_lon = route_coords[0]
    end_lat, end_lon = route_coords[-1]

    folium.Marker(
        [start_lat, start_lon],
        popup="Start",
        icon=folium.Icon(color="green"),
    ).add_to(m)

    folium.Marker(
        [end_lat, end_lon],
        popup="Ziel",
        icon=folium.Icon(color="red"),
    ).add_to(m)

    # Legende
    legend_html = """
     <div style="
        position: fixed;
        bottom: 50px;
        left: 50px;
        z-index: 9999;
        background-color: white;
        padding: 10px;
        border: 2px solid grey;
        border-radius: 5px;
        box-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        font-size: 12px;
     ">
       <b>Straßenzustand</b><br>
       <i style="background: green; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> VERY GOOD<br>
       <i style="background: lightgreen; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> GOOD<br>
       <i style="background: orange; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> FAIR<br>
       <i style="background: red; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> VERY POOR<br>
       <i style="background: gray; width: 12px; height: 12px; float: left; margin-right: 5px;"></i> NOT MEASURED<br>
     </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    m.save(output_html)

    return total_cost, total_dist_km, breakdown


# ------------------------------------------------------------
# Optionaler Test
# ------------------------------------------------------------
if __name__ == "__main__":
    dummy_route = [
        (50.1109, 8.6821),
        (50.1115, 8.6835),
        (50.1120, 8.6850),
    ]
    dummy_prices = {
        "VERY GOOD": 0.40,
        "GOOD": 0.50,
        "FAIR": 0.70,
        "VERY POOR": 0.90,
        "NOT MEASURED": 0.30,
    }

    cost, dist, breakdown = show_route_and_cost(dummy_route, dummy_prices, max_dist_m=2.0)
    print(f"Test: Distanz = {dist:.2f} km, Kosten = {cost:.2f} €")
    print("Aufschlüsselung:")
    for state, info in breakdown.items():
        print(
            f"  {state}: {info['dist_km']:.2f} km * "
            f"{info['price_per_km']:.2f} €/km = {info['cost']:.2f} €"
        )
