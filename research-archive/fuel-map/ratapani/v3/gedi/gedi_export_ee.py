"""Run on the PC (Earth Engine, project van-suraksha-alert). Exports GEDI L2B monthly rasterised shots over Ratapani to Drive as CSV:
one row per valid 25 m shot pixel with lon, lat, month, pai, pavd_z0 (0-5 m plant area volume density), pavd_z1 (5-10 m), cover, rh100 via L2A.
Then copy the CSV to /mnt/project-files/fuel-map/ratapani/v3/gedi/gedi_l2b_ratapani.csv and run gedi_compare.py there."""
import ee
ee.Initialize(project='van-suraksha-alert')
aoi = ee.Geometry.Rectangle([77.337, 22.816, 78.068, 23.107])
def prep(img):
    ok = img.select('l2b_quality_flag').eq(1).And(img.select('degrade_flag').eq(0)).And(img.select('sensitivity').gt(0.95))
    return img.select(['pai', 'pavd_z0', 'pavd_z1', 'cover']).updateMask(ok).set('month', img.date().format('YYYY-MM'))
col = ee.ImageCollection('LARSE/GEDI/GEDI02_B_002_MONTHLY').filterBounds(aoi).map(prep)
def to_pts(img):
    s = img.addBands(ee.Image.pixelLonLat()).sample(region=aoi, scale=25, geometries=False, dropNulls=True)
    return s.map(lambda f: f.set('month', img.get('month')))
fc = col.map(to_pts).flatten()
ee.batch.Export.table.toDrive(collection=fc, description='gedi_l2b_ratapani', fileFormat='CSV').start()
print('export started: gedi_l2b_ratapani.csv in Drive')
