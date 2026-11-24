"""One-time helper: turn U.S. state boundaries into SVG paths for the housing map.

Projects the lower 48 with an Albers equal-area projection (the standard for
U.S. maps), and draws Alaska and Hawaii as insets in the lower left.
Input: a state GeoJSON file (e.g. PublicaMundi/MappingAPI us-states.json).
Prints a JavaScript object to paste into housing/index.html.

Usage: python scripts/make_state_shapes.py us-states.json > shapes.js
"""
import json, math, sys

ABBR = {"Alabama":"AL","Alaska":"AK","Arizona":"AZ","Arkansas":"AR","California":"CA","Colorado":"CO",
 "Connecticut":"CT","Delaware":"DE","District of Columbia":"DC","Florida":"FL","Georgia":"GA","Hawaii":"HI",
 "Idaho":"ID","Illinois":"IL","Indiana":"IN","Iowa":"IA","Kansas":"KS","Kentucky":"KY","Louisiana":"LA",
 "Maine":"ME","Maryland":"MD","Massachusetts":"MA","Michigan":"MI","Minnesota":"MN","Mississippi":"MS",
 "Missouri":"MO","Montana":"MT","Nebraska":"NE","Nevada":"NV","New Hampshire":"NH","New Jersey":"NJ",
 "New Mexico":"NM","New York":"NY","North Carolina":"NC","North Dakota":"ND","Ohio":"OH","Oklahoma":"OK",
 "Oregon":"OR","Pennsylvania":"PA","Rhode Island":"RI","South Carolina":"SC","South Dakota":"SD",
 "Tennessee":"TN","Texas":"TX","Utah":"UT","Vermont":"VT","Virginia":"VA","Washington":"WA",
 "West Virginia":"WV","Wisconsin":"WI","Wyoming":"WY"}

def albers(p1, p2, lat0, lon0):
    p1, p2, lat0 = map(math.radians, (p1, p2, lat0))
    n = (math.sin(p1) + math.sin(p2)) / 2
    C = math.cos(p1) ** 2 + 2 * n * math.sin(p1)
    r0 = math.sqrt(C - 2 * n * math.sin(lat0)) / n
    def f(lon, lat):
        if lon > 0: lon -= 360          # Aleutians cross the date line
        r = math.sqrt(C - 2 * n * math.sin(math.radians(lat))) / n
        t = n * math.radians(lon - lon0)
        return r * math.sin(t), -(r0 - r * math.cos(t))
    return f

PROJ = {"lower": albers(29.5, 45.5, 37.5, -96), "AK": albers(55, 65, 50, -154), "HI": albers(8, 18, 3, -157)}

def polys(g):
    return [g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]

def simplify(pts, tol):
    if len(pts) < 4: return pts
    a, b = pts[0], pts[-1]; dmax, idx = 0, 0
    for i in range(1, len(pts) - 1):
        x, y = pts[i]; dx, dy = b[0] - a[0], b[1] - a[1]
        d = abs(dy * x - dx * y + b[0] * a[1] - b[1] * a[0]) / (math.hypot(dx, dy) or 1)
        if d > dmax: dmax, idx = d, i
    if dmax > tol: return simplify(pts[:idx + 1], tol)[:-1] + simplify(pts[idx:], tol)
    return [a, b]


def dist_to_edges(x, y, ring):
    best = float("inf")
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        dx, dy = bx - ax, by - ay
        t = max(0, min(1, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1)))
        best = min(best, math.hypot(x - ax - t * dx, y - ay - t * dy))
    return best

def inside(x, y, ring):
    c = False
    for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
        if (ay > y) != (by > y) and x < (bx - ax) * (y - ay) / (by - ay) + ax: c = not c
    return c

def label_point(ring, aspect=1.6):
    """Spot deepest inside the shape, with sideways room counting less (labels are wider than tall)."""
    xs = [p[0] for p in ring]; ys = [p[1] for p in ring]
    best = (-1, sum(xs) / len(xs), sum(ys) / len(ys))
    step = max(max(xs) - min(xs), max(ys) - min(ys)) / 40
    def score(x, y):
        if not inside(x, y, ring): return -1
        # distance to edges, measured with x squeezed so wide-but-short gaps don't win
        sq = [((px - x) / aspect + x, py) for px, py in ring]
        return dist_to_edges(x, y, sq)
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            sc = score(x, y)
            if sc > best[0]: best = (sc, x, y)
            x += step
        y += step
    for _ in range(3):   # refine around the best point
        step /= 4; bx, by = best[1], best[2]
        for i in range(-4, 5):
            for j in range(-4, 5):
                sc = score(bx + i * step, by + j * step)
                if sc > best[0]: best = (sc, bx + i * step, by + j * step)
    return best[1], best[2]

feats = {ABBR[f["properties"]["name"]]: f for f in json.load(open(sys.argv[1]))["features"] if f["properties"]["name"] in ABBR}
raw = {}
for ab, f in feats.items():
    pr = PROJ.get(ab, PROJ["lower"])
    raw[ab] = [[[pr(*pt) for pt in ring] for ring in poly] for poly in polys(f["geometry"])]

def bbox(keys):
    xs = [p[0] for k in keys for poly in raw[k] for ring in poly for p in ring]
    ys = [p[1] for k in keys for poly in raw[k] for ring in poly for p in ring]
    return min(xs), min(ys), max(xs), max(ys)

W = 960
lower = [k for k in raw if k not in ("AK", "HI")]
x0, y0, x1, y1 = bbox(lower); s = (W - 120) / (x1 - x0)     # leave room on the right for small-state boxes
H = round((y1 - y0) * s) + 20
place = {k: (s, x0, y0, 10, 10) for k in lower}
ax0, ay0, ax1, ay1 = bbox(["AK"]); sa = 190 / (ax1 - ax0); place["AK"] = (sa, ax0, ay0, 10, H - (ay1 - ay0) * sa - 10)
hx0, hy0, hx1, hy1 = bbox(["HI"]); sh = 110 / (hx1 - hx0); place["HI"] = (sh, hx0, hy0, 220, H - (hy1 - hy0) * sh - 14)

out = {"w": W, "h": H, "s": {}}
for ab, ps in raw.items():
    sc, ox, oy, tx, ty = place[ab]; d = []; best = (0, None)
    for poly in ps:
        for j, ring in enumerate(poly):
            pts = [((x - ox) * sc + tx, (y - oy) * sc + ty) for x, y in ring]
            if pts[0] == pts[-1]: pts = pts[:-1]
            m = len(pts) // 2   # closed ring: simplify each half so the endpoints differ
            pts = simplify(pts[:m + 1], 0.45)[:-1] + simplify(pts[m:] + pts[:1], 0.45)[:-1]
            if len(pts) < 3: continue
            d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
            if j == 0:   # remember the biggest outer ring; the label goes inside it
                A = sum(xa * yb - xb * ya for (xa, ya), (xb, yb) in zip(pts, pts[1:] + pts[:1]))
                if abs(A) > abs(best[0]): best = (A, pts)
    lx, ly = label_point(best[1])
    out["s"][ab] = {"d": "".join(d), "c": [round(lx, 1), round(ly, 1)], "a": round(abs(best[0]) / 2)}
print(json.dumps(out, separators=(",", ":")))
