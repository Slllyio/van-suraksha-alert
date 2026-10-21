import json, math
from shapely.geometry import shape, Point, box, mapping
from shapely.validation import make_valid
from shapely.strtree import STRtree
from . import config


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


class Beats:
    """Point-in-beat lookup over the beats GeoJSON."""

    def __init__(self, path=None):
        path = path or config.BEATS_PATH
        self.fc = json.load(open(path, encoding="utf-8"))
        self.props, geoms = [], []
        for f in self.fc["features"]:
            self.props.append(f["properties"])
            g = shape(f["geometry"])
            geoms.append(g if g.is_valid else make_valid(g))
        self.geoms = geoms
        self.tree = STRtree(geoms)
        self.by_uid = {p["beat_uid"]: p for p in self.props}
        self._light = {}

    def in_box(self, x0, y0, x1, y1, limit=3000):
        """Simplified beat outlines inside a map view (the full MP layer is too big to send)."""
        out = []
        for i in self.tree.query(box(x0, y0, x1, y1))[:limit]:
            i = int(i)
            if i not in self._light:
                self._light[i] = mapping(self.geoms[i].simplify(0.0004))
            out.append({"type": "Feature", "properties": self.props[i], "geometry": self._light[i]})
        return {"type": "FeatureCollection", "features": out}

    def in_range(self, range_name):
        """Beats of a range. 'Division:Range' disambiguates range names used in two divisions."""
        if ":" in (range_name or ""):
            div, rng = range_name.split(":", 1)
            return [p["beat_uid"] for p in self.props if p["range"] == rng and p.get("division") == div]
        return [p["beat_uid"] for p in self.props if p["range"] == range_name]

    def locate(self, lat, lon):
        pt = Point(lon, lat)
        for i in self.tree.query(pt, predicate="intersects"):
            return self.props[int(i)]["beat_uid"]
        return None

    def touching(self, lat, lon, radius_km):
        """Beats within radius_km of the point (the fire pixel's footprint), nearest first."""
        r = radius_km / 111.32
        pt = Point(lon, lat)
        area = pt.buffer(r)
        hits = [(self.geoms[int(i)].distance(pt), self.props[int(i)]["beat_uid"])
                for i in self.tree.query(area, predicate="intersects")]
        return [u for _, u in sorted(hits)]

    def name(self, uid):
        p = self.by_uid.get(uid or "")
        return f"{p['beat']} ({p['range']})" if p else (uid or "outside beats")


class Mask:
    """FSI-style 500 m mask around industry, mines, quarries, solar, power plants, kilns, landfills."""

    def __init__(self, path=None):
        path = path or config.MASK_PATH
        self.kinds, geoms = [], []
        try:
            fc = json.load(open(path, encoding="utf-8"))
        except FileNotFoundError:
            fc = {"features": []}
        for f in fc["features"]:
            g = shape(f["geometry"])
            for part in getattr(g, "geoms", [g]):
                geoms.append(part)
                self.kinds.append(f["properties"]["kind"])
        self.geoms = geoms
        self.tree = STRtree(geoms) if geoms else None

    def hit(self, lat, lon):
        if self.tree is None:
            return None
        for i in self.tree.query(Point(lon, lat), predicate="intersects"):
            return self.kinds[int(i)]
        return None
