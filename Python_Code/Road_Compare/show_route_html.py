import csv
import math
from pathlib import Path
import folium
import webbrowser
import psycopg2
from psycopg2 import OperationalError

# ============================================================
# DB-Konfiguration (wie in Check.py)
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

# maximaler Abstand eines DB-Punkts zur Route,
# damit er als "auf dieser Strecke" gilt (in Metern)
MAX_DIST_M = 15.0


# ============================================================
# 1) Route aus CSV laden
#    - bevorzugt: lat_matched / lon_matched
#    - fallback: lat / lon
# ============================================================
def load_coords_from_csv(csv_path: Path):
    coords = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            print("⚠️ CSV hat keine Headerzeile.")
            return []

        fieldnames = [name.strip() for name in reader.fieldnames]

        # Spalten automatisch erkennen
        if "lat_matched" in fieldnames and "lon_matched" in fieldnames:
            lat_col = "lat_matched"
            lon_col = "lon_matched"
            print("Verwende Spalten lat_matched / lon_matched aus der CSV.")
        elif "lat" in fieldnames and "lon" in fieldnames:
            lat_col = "lat"
            lon_col = "lon"
            print("Verwende Spalten lat / lon aus der CSV.")
        else:
            print("⚠️ Konnte keine passenden Spalten für Koordinaten finden.")
            print("Gefundene Spalten:", fieldnames)
            return []

        for row in reader:
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
                coords.append((lat, lon))
            except (KeyError, ValueError, TypeError):
                continue

    return coords


# ============================================================
# 2) Punkte + Zustand AUS DER SQL-DATENBANK LADEN
# ============================================================
def load_db_points():
    """
    Holt alle (lat, lon, roughness) aus track_point
    und gibt eine Liste von Dicts zurück.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
    except OperationalError as e:
        print("⚠️ Konnte nicht auf die Datenbank zugreifen. Route wird ohne Farben angezeigt.")
        print("Details:", e)
        return []

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
                "state": str(roughness).upper(),
            }
        )

    cur.close()
    conn.close()

    print(f"{len(db_points)} Punkte mit Zustand aus der DB geladen.")
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
# 3) Geometrie-Helfer: Abstand Punkt -> Strecken-Segment
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


def find_segment_state(lat1, lon1, lat2, lon2, db_points, lat0):
    """
    Sucht alle DB-Punkte, die in der Nähe dieses Segments liegen,
    und gibt den „schlechtesten“ gefundenen Zustand zurück.
    """
    best_state = None

    for p in db_points:
        d = point_to_segment_distance_m(
            p["lat"], p["lon"], lat1, lon1, lat2, lon2, lat0
        )
        if d <= MAX_DIST_M:
            best_state = choose_worse_state(best_state, p["state"])

    return best_state


# ============================================================
# 4) Karte bauen: Route + farbige Segmente + Legende
# ============================================================
def create_route_map(coords, db_points, output_html: Path):
    if not coords:
        raise ValueError("Keine Koordinaten übergeben.")

    avg_lat = sum(lat for lat, _ in coords) / len(coords)
    avg_lon = sum(lon for _, lon in coords) / len(coords)

    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=14)

    # Basisroute in hellgrau
    folium.PolyLine(
        coords,
        tooltip="Route",
        weight=3,
        color="lightgray",
    ).add_to(m)

    segments_colored = 0

    # jetzt Segment für Segment einfärben,
    # wenn passende DB-Punkte in der Nähe sind
    for i in range(len(coords) - 1):
        lat1, lon1 = coords[i]
        lat2, lon2 = coords[i + 1]

        segment_state = find_segment_state(lat1, lon1, lat2, lon2, db_points, avg_lat)

        if not segment_state:
            continue  # kein DB-Punkt in der Nähe -> bleibt grau

        color = STATE_COLORS.get(segment_state, "blue")

        folium.PolyLine(
            [(lat1, lon1), (lat2, lon2)],
            weight=6,
            color=color,
            tooltip=f"Zustand: {segment_state}",
        ).add_to(m)
        segments_colored += 1

    print(f"{segments_colored} von {len(coords) - 1} Segmenten wurden eingefärbt.")

    # Start / Ziel markieren
    start_lat, start_lon = coords[0]
    end_lat, end_lon = coords[-1]

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

    m.save(str(output_html))


# ============================================================
# 5) main(): in DB_PostgreSQL **und** Elternordner nach CSV suchen
#    und route_matched_* bevorzugen
# ============================================================
def main():
    base_dir = Path(__file__).resolve().parent      # .../Code_GPS/DB_PostgreSQL
    parent_dir = base_dir.parent                   # .../Code_GPS

    print(f"Suche CSV-Dateien in: {base_dir} und {parent_dir}")

    route_files = []

    # 1. Gematchte Routen bevorzugen
    route_files.extend(sorted(base_dir.glob("route_matched_*.csv")))
    route_files.extend(sorted(parent_dir.glob("route_matched_*.csv")))

    # 2. Falls keine gematchten vorhanden: normale route_*.csv
    if not route_files:
        print("Keine route_matched_*.csv gefunden – versuche route_*.csv.")
        route_files.extend(sorted(base_dir.glob("route_*.csv")))
        route_files.extend(sorted(parent_dir.glob("route_*.csv")))

    if not route_files:
        print("Keine route_matched_*.csv oder route_*.csv in den Suchordnern gefunden.")
        return

    # Neuste Datei verwenden
    csv_path = sorted(route_files)[-1]
    print(f"Nutze Datei: {csv_path}")

    coords = load_coords_from_csv(csv_path)
    if not coords:
        print("Keine gültigen Koordinaten in der CSV gefunden.")
        return

    db_points = load_db_points()

    html_path = base_dir / "route_preview.html"
    create_route_map(coords, db_points, html_path)

    print(f"Karte gespeichert als: {html_path}")
    webbrowser.open(html_path.as_uri())


if __name__ == "__main__":
    main()
