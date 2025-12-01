import pandas as pd
import psycopg2
import numpy as np  # falls NumPy-Skalare vorkommen


HOST = "roadquality-db.ce9gmcmsmoc6.us-east-1.rds.amazonaws.com"
PORT = 5432
DBNAME = "postgres"          # oder "roadquality"
USER = "UAS"
PASSWORD = "UAS2025!"

#finde für mich den Pfad zur CSV-Datei mit den gematchten Punkten


CSV_FILE = "c:\\Users\\alzub\\OneDrive - Frankfurt UAS\\MeRo2\\MERO_Code\\Python_Code\\Find_IRI\\RoadLabPro\\f_Link_0002_Path_2025_11_17_08_33_matched.csv"  # nur lat_matched, lon_matched, Roughness


def to_float(v):
    """Versucht einen Wert robust nach float zu konvertieren, sonst None."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except TypeError:
        pass

    s = str(v).strip()
    if s == "":
        return None
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def to_py(v):
    """
    Wandelt NumPy-Skalare (z.B. numpy.int64, numpy.float64)
    in normale Python-Typen um.
    """
    if v is None:
        return None
    if isinstance(v, np.generic):
        return v.item()
    return v


def main():
    # -----------------------------------------------------------------
    # 0) CSV laden
    # -----------------------------------------------------------------
    df = pd.read_csv(CSV_FILE)
    print("Spalten in der CSV:", list(df.columns))

    # Sicherstellen, dass die benötigten Spalten vorhanden sind
    required_cols = {"lat_matched", "lon_matched", "Roughness"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Folgende Spalten fehlen in der CSV: {missing}")

    # -----------------------------------------------------------------
    # 1) DB-Verbindung herstellen
    # -----------------------------------------------------------------
    conn = psycopg2.connect(
        host=HOST,
        port=PORT,
        dbname=DBNAME,
        user=USER,
        password=PASSWORD,
        sslmode="require",
    )
    cur = conn.cursor()

    # -----------------------------------------------------------------
    # 1a) ALLE bestehenden track_point-Daten löschen
    # -----------------------------------------------------------------
    print("Lösche alle bestehenden Einträge in track_point ...")
    cur.execute("DELETE FROM track_point;")
    conn.commit()
    print("Alle Einträge in track_point wurden gelöscht.")

    # Optional: einmal leer zählen
    cur.execute("SELECT COUNT(*) FROM track_point;")
    count_after_delete = cur.fetchone()[0]
    print("Zeilen in track_point nach dem Löschen:", count_after_delete)

    # -----------------------------------------------------------------
    # 2) Track-Points importieren (nur 3 Spalten)
    # -----------------------------------------------------------------
    inserted = 0

    for _, row in df.iterrows():
        lat_m = to_float(row.get("lat_matched"))
        lon_m = to_float(row.get("lon_matched"))

        roughness = row.get("Roughness")
        # Roughness optional als Text bereinigen
        if isinstance(roughness, str):
            roughness = roughness.strip()
            if roughness == "":
                roughness = None
        roughness = to_py(roughness)

        # Falls lat/lon nicht vorhanden, Zeile überspringen
        if lat_m is None or lon_m is None:
            continue

        params = (lat_m, lon_m, roughness)

        cur.execute(
            """
            INSERT INTO track_point (
                lat_matched,
                lon_matched,
                roughness
            )
            VALUES (%s, %s, %s)
            """,
            params,
        )
        inserted += 1

    conn.commit()
    cur.close()
    conn.close()

    print(f"{inserted} Zeilen aus der CSV neu importiert.")


if __name__ == "__main__":
    main()
