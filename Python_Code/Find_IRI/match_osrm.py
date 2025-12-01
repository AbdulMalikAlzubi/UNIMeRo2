import pandas as pd
import requests
import math
from pathlib import Path

# ==============================
# 1. KONFIGURATION
# ==============================

# OSRM-Server:
# - Public Demo: "https://router.project-osrm.org"
# - Eigener Server: z.B. "http://localhost:5000"
OSRM_BASE_URL = "https://router.project-osrm.org"

# Ordner, in dem dieses Skript liegt (AWS_Creat)
BASE_DIR = Path(__file__).resolve().parent

# RoadLab-Path-CSV (GPS-Punkte)
INPUT_CSV = BASE_DIR.parent / "Find_IRI" / "RoadLabPro" / "f_Link_0002_Path_2025_11_17_08_33.csv"

# RoadLab-Roughness-/IRI-CSV (Zustand pro Interval)
ROUGHNESS_CSV = BASE_DIR.parent / "Find_IRI" / "RoadLabPro" / "f_Link_0002_Roughness_2025_11_17_08_33.csv"

# Ausgabe-Datei (mit gesnappten Punkten + Zustand)
OUTPUT_CSV = BASE_DIR.parent / "Find_IRI" / "f_Link_0002_Path_2025_11_17_08_33_matched.csv"

# ==============================
# 2. CSV EINLESEN UND VORBEREITEN
# ==============================

print("Lese CSV ein:", INPUT_CSV)
df = pd.read_csv(INPUT_CSV)

# Zeitstempel steht in deinem Export im Index (z. B. "08:32:40 2025-November-17")
# -> Index in Spalte holen und in datetime umwandeln
df = df.rename_axis("timestamp_str").reset_index()
df["timestamp"] = pd.to_datetime(df["timestamp_str"])

# Lat/Lon aus RoadLab (in deinem Export so beobachtet):
# Interval_Number ≈ Breitengrad (lat, ca. 50.x)
# Point_Latitude  ≈ Längengrad (lon, ca. 8.x)
df["lat"] = df["Interval_Number"]
df["lon"] = df["Point_Latitude"]

# Sicherheitsfilter: Koordinaten (0,0) entfernen
df = df[(df["lat"] != 0) & (df["lon"] != 0)].reset_index(drop=True)

print("Anzahl Punkte nach Filter:", len(df))


# ==============================
# 3. FUNKTION: EINEN CHUNK MIT OSRM MAP MATCHING SCHICKEN
# ==============================

def match_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    """
    Einen Teil-Track (max. ca. 100 Punkte) an die OSRM-API (/match)
    schicken und gesnappte Koordinaten zurückbekommen.
    """
    if len(chunk) == 0:
        return chunk

    # Koordinaten-String: lon,lat;lon,lat;...
    coords = ";".join(f"{row.lon:.6f},{row.lat:.6f}" for row in chunk.itertuples())

    # Unix-Zeitstempel (Sekunden seit 1970)
    timestamps = ";".join(str(int(row.timestamp.timestamp())) for row in chunk.itertuples())

    url = f"{OSRM_BASE_URL}/match/v1/driving/{coords}"
    params = {
        "geometries": "geojson",
        "overview": "full",
        "timestamps": timestamps,
        # Optional: maximale Distanz zum nächsten Straßenpunkt in Metern
        # "radiuses": ";".join(["25"] * len(chunk)),
    }

    print(f"  -> Sende {len(chunk)} Punkte an OSRM /match ...")
    r = requests.get(url, params=params)

    if r.status_code != 200:
        print("OSRM-Status:", r.status_code)
        print("Antwort:", r.text)
        r.raise_for_status()

    data = r.json()

    # OSRM /match liefert auch ein Feld "tracepoints"
    tracepoints = data.get("tracepoints", [])

    matched_lats = []
    matched_lons = []

    # tracepoints-Länge sollte = Anzahl input-Punkte sein
    for tp in tracepoints:
        if tp is None:
            # Punkt konnte nicht gematcht werden
            matched_lats.append(math.nan)
            matched_lons.append(math.nan)
        else:
            lon_m, lat_m = tp["location"]  # [lon, lat]
            matched_lats.append(lat_m)
            matched_lons.append(lon_m)

    out = chunk.copy()
    out["lat_matched"] = matched_lats
    out["lon_matched"] = matched_lons
    return out


# ==============================
# 4. TRACK IN CHUNKS TEILEN & MATCHEN
# ==============================

# OSRM kann bis zu ca. 100 Koordinaten pro Request, wir nehmen 80 zur Sicherheit
chunk_size = 80
chunks = [df.iloc[i:i + chunk_size] for i in range(0, len(df), chunk_size)]

matched_chunks = []
for i, ch in enumerate(chunks, start=1):
    print(f"Bearbeite Chunk {i}/{len(chunks)} mit {len(ch)} Punkten...")
    matched_chunks.append(match_chunk(ch))

df_matched = pd.concat(matched_chunks, ignore_index=True)

print("Map Matching (OSRM) fertig, Gesamtpunkte:", len(df_matched))


# ==============================
# 4b. ROUGHNESS / IRI DAZUJOINEN
# ==============================

print("Lese Roughness-CSV ein:", ROUGHNESS_CSV)
df_rough = pd.read_csv(ROUGHNESS_CSV)

print("Spalten in Roughness-CSV:", df_rough.columns.tolist())

# Nur relevante Spalten auswählen und bei Bedarf hier anpassen:
# Mindestens: Interval_Number, Roughness
rough_cols = ["Interval_Number", "Roughness"]
# Falls eine IRI-Spalte existiert, einfach hinzufügen:
# rough_cols = ["Interval_Number", "Roughness", "IRI"]

df_rough_small = df_rough[rough_cols].copy()

# Nach Interval_Number sortieren (wichtig für merge_asof)
df_matched_sorted = df_matched.sort_values("Interval_Number")
df_rough_sorted = df_rough_small.sort_values("Interval_Number")

# Nächsten passenden Roughness-Eintrag an jeden Punkt hängen
df_final = pd.merge_asof(
    df_matched_sorted,
    df_rough_sorted,
    on="Interval_Number",
    direction="nearest"
)

print("Nach Join: Spalten in df_final:", df_final.columns.tolist())


# ==============================
# 5. ERGEBNIS ALS NEUE CSV SPEICHERN
# ==============================

# Nur relevante Spalten behalten
df_final = df_final[["lat_matched", "lon_matched", "Roughness"]]

# Optional: nur Zeilen mit gültigen Matches
# df_final = df_final.dropna(subset=["lat_matched", "lon_matched"])

df_final.to_csv(OUTPUT_CSV, index=False)
print("Gespeichert als:", OUTPUT_CSV)
print("Fertig! :)")
