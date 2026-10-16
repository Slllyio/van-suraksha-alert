"""Export quality-filtered GEDI L2B shots (pai, pavd_z0, pavd_z1, cover) over Ratapani to CSV."""
import ee
import pandas as pd

ee.Initialize(project='van-suraksha-alert')
BANDS = ['pai', 'pavd_z0', 'pavd_z1', 'cover']
BBOX = (77.337, 22.816, 78.068, 23.107)
col = ee.ImageCollection('LARSE/GEDI/GEDI02_B_002_MONTHLY').filterBounds(ee.Geometry.Rectangle(BBOX))


def sample(img, bbox):
    """Sample a bbox; split into 4 quadrants when the getInfo 5000-element cap is hit."""
    x0, y0, x1, y1 = bbox
    try:
        return img.sample(region=ee.Geometry.Rectangle(bbox), scale=25,
                          geometries=False, dropNulls=True).getInfo()['features']
    except ee.EEException as e:
        if '5000' not in str(e) and 'too many' not in str(e).lower():
            raise
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    quads = [(x0, y0, mx, my), (mx, y0, x1, my), (x0, my, mx, y1), (mx, my, x1, y1)]
    return [f for q in quads for f in sample(img, q)]


rows = []
for d in col.aggregate_array('system:index').getInfo():
    img = ee.Image(col.filter(ee.Filter.eq('system:index', d)).first())
    ok = (img.select('l2b_quality_flag').eq(1)
          .And(img.select('degrade_flag').eq(0))
          .And(img.select('sensitivity').gt(0.95)))
    s = img.select(BANDS).updateMask(ok).addBands(ee.Image.pixelLonLat())
    month = ee.Date(img.get('system:time_start')).format('YYYY-MM').getInfo()
    feats = sample(s, BBOX)
    rows += [dict(p['properties'], month=month) for p in feats]
    print(d, month, len(feats), flush=True)

df = pd.DataFrame(rows)[['longitude', 'latitude', 'month'] + BANDS]
df.to_csv('gedi_l2b_ratapani.csv', index=False)
print('rows', len(df), 'months', df.month.min(), df.month.max(), df.month.nunique())
