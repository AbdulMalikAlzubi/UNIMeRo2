from fastapi import FastAPI, HTTPException
import psycopg2
import math
import os

# ============================================================
# DB-Konfiguration
# ============================================================
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "roadquality-db.ce9gmcmsmoc6.us-east-1.rds.amazonaws.com"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "UAS"),
    "password": os.getenv("DB_PASSWORD", "UAS2025!"),
    "sslmode": os.getenv("DB_SSLMODE", "require"),
}

app = FastAPI(title="Road State API")


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


def haversine_distance_m(lat1, lon1, lat2, lon2):
    """Entfernung zwischen zwei GPS-Punkten in Metern."""
    R = 6371000.0  # Erdradius in m
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/road_state")
def road_state(lat: float, lon: float, radius_m: int = 50):
    """
    Gibt NUR den Zustand (state) des nächstgelegenen Messpunkts zurück.
    Erwartet lat, lon, optional radius_m in Metern.
    """

    # 1) grobe Bounding Box um die Anfrageposition
    lat_radius_deg = radius_m / 111_320.0
    lon_radius_deg = radius_m / (111_320.0 * math.cos(math.radians(lat)))

    min_lat = lat - lat_radius_deg
    max_lat = lat + lat_radius_deg
    min_lon = lon - lon_radius_deg
    max_lon = lon + lon_radius_deg

    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # WICHTIG: Spaltennamen an deine Tabelle anpassen
        cur.execute(
            """
            SELECT lat_matched, lon_matched, roughness
            FROM track_point
            WHERE lat_matched BETWEEN %s AND %s
              AND lon_matched BETWEEN %s AND %s
            """,
            (min_lat, max_lat, min_lon, max_lon),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not rows:
        raise HTTPException(status_code=404, detail="No points near this location")

    # 2) exakten nächsten Punkt finden
    best_row = None
    best_dist = None

    for r in rows:
        lat_m = r[0]
        lon_m = r[1]
        roughness = r[2]  # hier steckt bei dir 'GOOD', 'FAIR', ...
        dist = haversine_distance_m(lat, lon, lat_m, lon_m)

        if best_dist is None or dist < best_dist:
            best_dist = dist
            best_row = roughness

    if best_row is None or best_dist is None or best_dist > radius_m:
        raise HTTPException(status_code=404, detail="No points within radius")

    # Zustand als Großbuchstaben zurückgeben
    state = str(best_row).upper()

    return {"state": state}
