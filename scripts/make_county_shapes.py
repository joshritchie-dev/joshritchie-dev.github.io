"""One-time helper: turn U.S. Census county boundaries into SVG paths for the map.

Input: a county GeoJSON file (e.g. plotly/datasets geojson-counties-fips.json,
which is drawn from Census cartographic boundary files).
Output: data/traffic/mi_counties.json with one SVG path per Michigan county.

Usage: python scripts/make_county_shapes.py counties.json data/traffic/mi_counties.json
"""
import json, math, sys
src, out = sys.argv[1], sys.argv[2]
d = json.load(open(src))
feats = [f for f in d["features"] if f["id"].startswith("26")]
lat0 = math.radians(44.6); k = math.cos(lat0)
def proj(lon, lat): return lon * k, -lat
pts = []
def rings(g):
    if g["type"] == "Polygon": return [g["coordinates"]]
    return g["coordinates"]
for f in feats:
    for poly in rings(f["geometry"]):
        for ring in poly:
            pts += [proj(*p) for p in ring]
minx = min(p[0] for p in pts); maxx = max(p[0] for p in pts)
miny = min(p[1] for p in pts); maxy = max(p[1] for p in pts)
W = 1000.0; s = W / (maxx - minx); H = (maxy - miny) * s
res = {"width": round(W), "height": round(H), "counties": {}}
for f in feats:
    parts = []; cx = cy = n = 0
    for poly in rings(f["geometry"]):
        for ring in poly:
            seg = []; last = None
            for lon, lat in ring:
                x, y = proj(lon, lat); x = round((x - minx) * s, 1); y = round((y - miny) * s, 1)
                if (x, y) != last: seg.append(f"{x:g},{y:g}"); last = (x, y)
                cx += x; cy += y; n += 1
            parts.append("M" + "L".join(seg) + "Z")
    name = f["properties"]["NAME"]
    res["counties"][name] = {"fips": f["id"], "d": "".join(parts)}
json.dump(res, open(out, "w"), separators=(",", ":"))
print(len(res["counties"]), res["width"], res["height"], sorted(res["counties"])[:5], [n for n in res["counties"] if "St" in n])
