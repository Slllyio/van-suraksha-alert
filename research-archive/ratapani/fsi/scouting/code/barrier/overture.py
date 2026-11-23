import duckdb,sys
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
R='2026-09-23.0'
con=duckdb.connect(); con.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
for theme,typ,cols in [('transportation','segment',"subtype, class, names.primary as name, sources[1].dataset as src"),
                       ('base','water',"subtype, class, names.primary as name, sources[1].dataset as src"),
                       ('base','land_use',"subtype, class, sources[1].dataset as src"),
                       ('base','infrastructure',"subtype, class, sources[1].dataset as src"),
                       ('base','land',"subtype, class, sources[1].dataset as src")]:
    q=f"""COPY (SELECT id, {cols}, geometry FROM read_parquet('s3://overturemaps-us-west-2/release/{R}/theme={theme}/type={typ}/*', hive_partitioning=1)
      WHERE bbox.xmin<78.3 AND bbox.xmax>77.4 AND bbox.ymin<23.3 AND bbox.ymax>22.7) TO '{D}overture_{typ}.geojson' WITH (FORMAT GDAL, DRIVER 'GeoJSON')"""
    try:
        con.execute(q); print(typ, con.execute(f"select count(*) from st_read('{D}overture_{typ}.geojson')").fetchall())
    except Exception as e: print(typ,'ERR',str(e)[:300])
