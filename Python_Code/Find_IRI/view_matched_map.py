import pandas as pd
import folium

CSV_FILE = "f_Link_0002_Path_2025_11_17_08_33_matched.csv"

df = pd.read_csv(CSV_FILE)
df = df.dropna(subset=["lat_matched", "lon_matched"])

roughness_col = "Roughness"  # ggf. anpassen

def roughness_to_color(r):
    if r == "VERY GOOD":
        return "green"
    elif r == "GOOD":
        return "lime"
    elif r == "FAIR":
        return "orange"
    elif r == "POOR":
        return "red"
    elif r == "VERY POOR":
        return "darkred"
    else:
        return "gray"

center_lat = df["lat_matched"].mean()
center_lon = df["lon_matched"].mean()
m = folium.Map(location=[center_lat, center_lon], zoom_start=15)

# Für jedes Segment [Punkt i -> i+1] eine Teil-Linie mit eigener Farbe
for i in range(len(df) - 1):
    r = df.iloc[i][roughness_col]
    color = roughness_to_color(r)

    p1 = (df.iloc[i]["lat_matched"], df.iloc[i]["lon_matched"])
    p2 = (df.iloc[i+1]["lat_matched"], df.iloc[i+1]["lon_matched"])

    folium.PolyLine(
        [p1, p2],
        color=color,
        weight=6,
        opacity=0.9,
        tooltip=f"Roughness: {r}"
    ).add_to(m)

m.save("matched_track_with_iri_segments.html")
print("Karte gespeichert als matched_track_with_iri_segments.html")
