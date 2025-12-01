import psycopg2

HOST = "roadquality-db.ce9gmcmsmoc6.us-east-1.rds.amazonaws.com"
PORT = 5432
DBNAME = "postgres"          # oder "roadquality"
USER = "UAS"
PASSWORD = "UAS2025!"

def main():
    conn = psycopg2.connect(
        host=HOST,
        port=PORT,
        dbname=DBNAME,
        user=USER,
        password=PASSWORD,
        sslmode="require",
    )
    cur = conn.cursor()

    # 1) Wieviel ist drin?
    cur.execute("SELECT COUNT(*) FROM track_point;")
    total = cur.fetchone()[0]
    print("Anzahl Zeilen in track_point:", total)

    # 2) Ein paar Beispielzeilen ansehen
    cur.execute("""
        SELECT lat_matched, lon_matched, roughness
        FROM track_point
        ORDER BY ctid   -- einfache Reihenfolge
        LIMIT 20;
    """)
    rows = cur.fetchall()
    print("\nBeispielzeilen:")
    for r in rows:
        print(r)

    # 3) Welche Roughness-Werte kommen vor?
    cur.execute("""
        SELECT roughness, COUNT(*) 
        FROM track_point
        GROUP BY roughness
        ORDER BY roughness;
    """)
    stats = cur.fetchall()
    print("\nRoughness-Verteilung:")
    for rough, cnt in stats:
        print(f"{rough}: {cnt}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
