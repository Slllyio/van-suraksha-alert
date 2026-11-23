import xml.etree.ElementTree as ET, json, sys
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
ns={'k':'http://www.opengis.net/kml/2.2'}
root=ET.parse(sys.argv[1]).getroot()
out=[]
for pm in root.iter('{http://www.opengis.net/kml/2.2}Placemark'):
    name=(pm.findtext('k:name',default='',namespaces=ns) or '').strip()
    d={s.get('name'):s.text for s in pm.iter('{http://www.opengis.net/kml/2.2}SimpleData')}
    polys=[]
    for pg in pm.iter('{http://www.opengis.net/kml/2.2}Polygon'):
        ob=pg.find('k:outerBoundaryIs/k:LinearRing/k:coordinates',ns)
        holes=[h.text for h in pg.findall('k:innerBoundaryIs/k:LinearRing/k:coordinates',ns)]
        f=lambda t:[tuple(map(float,c.split(',')[:2])) for c in t.split()]
        try: polys.append(Polygon(f(ob.text),[f(h) for h in holes]).buffer(0))
        except Exception as e: pass
    g=unary_union(polys) if polys else None
    out.append(dict(name=name,**d,geom=g))
import pickle; pickle.dump(out,open(sys.argv[2],'wb'))
from collections import Counter
print(Counter(o.get('DESIG') for o in out))
print(Counter(o.get('state_name') for o in out).most_common(40))
for o in out:
    if (o.get('state_name') or '').upper().startswith('MADHYA') or (o.get('DESIG') or '').lower().startswith('tiger'):
        g=o['geom']; print(o['name'],'|',o.get('DESIG'),'|',o.get('state_name'),'|',o.get('REP_AREA'), '| bounds', None if g is None else [round(x,2) for x in g.bounds])
