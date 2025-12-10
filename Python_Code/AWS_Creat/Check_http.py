import requests
import json
from pathlib import Path

BASE_URL = "http://100.25.221.124:8000"    # deine FastAPI-URL
BACKUP_FILE = "track_points_backup.json"   # lokale Datei


def backup_points():
    """Alle Punkte von der API holen und lokal in einer JSON-Datei speichern."""
    print("▶ Hole Punkte von der API...")
    resp = requests.get(f"{BASE_URL}/db_points")
    resp.raise_for_status()
    data = resp.json()

    print(f"  {len(data)} Punkte erhalten, speichere in {BACKUP_FILE}...")
    Path(BACKUP_FILE).write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("✅ Backup fertig.\n")


def delete_all_points():
    """Alle Punkte in der DB über die API löschen."""
    print("▶ Lösche alle Punkte in der DB...")
    resp = requests.delete(f"{BASE_URL}/track_points")
    # Optional: wenn dein Endpoint anders heißt, hier anpassen
    if resp.status_code != 200:
        print("❌ Fehler beim Löschen:", resp.status_code, resp.text)
        return
    print("✅ Antwort der API:", resp.json(), "\n")


def restore_points():
    """Punkte aus der lokalen JSON-Datei wieder in die DB schreiben."""
    print(f"▶ Lese Backup aus {BACKUP_FILE}...")
    text = Path(BACKUP_FILE).read_text(encoding="utf-8")
    data = json.loads(text)
    print(f"  {len(data)} Punkte im Backup gefunden.")
    
    count_ok = 0
    for row in data:
        # Robust gegen unterschiedliche JSON-Strukturen
        lat = row.get("lat") or row.get("lat_matched")
        lon = row.get("lon") or row.get("lon_matched")
        roughness = row.get("roughness") or row.get("state")

        payload = {
            "lat_matched": lat,
            "lon_matched": lon,
            "roughness": roughness,
        }

        resp = requests.post(f"{BASE_URL}/track_points", json=payload)
        if resp.status_code == 200:
            count_ok += 1
        else:
            print("❌ Fehler beim Insert:", resp.status_code, resp.text)
            # du könntest hier auch abbrechen mit `break`

    print(f"✅ {count_ok} Punkte wieder in die DB geschrieben.\n")


def main():
    # Beispiel-Ablauf:
    # 1) Backup machen
    backup_points()

    # 2) Alles in der DB löschen
    delete_all_points()

    # 3) Wiederherstellen
    # (wenn du das erst später machen willst, kommentier die nächste Zeile aus
    #  und führ das Skript später nochmal nur mit restore_points() aus)
    restore_points()


if __name__ == "__main__":
    main()
