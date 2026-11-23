"""Layer 2: Overture Maps 2026-09-23 'divisions/division' points (localities: cities, towns, villages, hamlets) for the MP bbox,
read by HTTP range requests of the parquet row groups whose bbox statistics intersect MP (no key, no install; same reader as
early_burns/b2_overture_roads.py). Output (scratch): ov/places_mp.parquet (subtype, class, lon, lat)."""
import requests, io, re, pyarrow.parquet as pq, pyarrow as pa, pyarrow.compute as pc, concurrent.futures as cf, shapely
B = 'https://overturemapswestus2.blob.core.windows.net/release'; REL = '2026-09-23.0'; X0, X1, Y0, Y1 = 74.0, 82.9, 21.0, 26.9
S = requests.Session()
class HF(io.RawIOBase):
    def __init__(s, u): s.u = u; s.p = 0; s.n = int(S.head(u).headers['Content-Length'])
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.p
    def seek(s, o, w=0): s.p = o if w == 0 else (s.p + o if w == 1 else s.n + o); return s.p
    def read(s, k=-1):
        if k is None or k < 0: k = s.n - s.p
        if k == 0 or s.p >= s.n: return b''
        e = min(s.p + k, s.n) - 1
        for t in range(5):
            try: r = S.get(s.u, headers={'Range': f'bytes={s.p}-{e}'}, timeout=120); r.raise_for_status(); break
            except Exception:
                if t == 4: raise
        b = r.content; s.p += len(b); return b
    def readinto(s, b): d = s.read(len(b)); b[:len(d)] = d; return len(d)
def run(theme, typ, out):
    x = S.get(B, params={'restype': 'container', 'comp': 'list', 'prefix': f'{REL}/theme={theme}/type={typ}/'}).text
    names = re.findall('<Name>([^<]*)</Name>', x)
    def hits(name):
        f = pq.ParquetFile(HF(f'{B}/{name}')); md = f.metadata
        cols = {md.row_group(0).column(j).path_in_schema: j for j in range(md.row_group(0).num_columns)}
        ix = {k: cols[f'bbox.{k}'] for k in ['xmin', 'xmax', 'ymin', 'ymax']}; h = []
        for i in range(md.num_row_groups):
            st = {k: md.row_group(i).column(j).statistics for k, j in ix.items()}
            if st['xmin'].min <= X1 and st['xmax'].max >= X0 and st['ymin'].min <= Y1 and st['ymax'].max >= Y0: h.append(i)
        return name, h
    with cf.ThreadPoolExecutor(16) as ex: res = [r for r in ex.map(hits, names) if r[1]]
    print(theme, typ, 'files', len(res), 'row groups', sum(len(h) for _, h in res), flush=True)
    def get(nh):
        name, i = nh; f = pq.ParquetFile(HF(f'{B}/{name}'))
        cs = [c for c in ('subtype', 'class', 'bbox', 'geometry') if c in f.schema_arrow.names]
        t = f.read_row_group(i, columns=cs); bb = t.column('bbox').combine_chunks()
        m = pc.and_(pc.and_(pc.less_equal(bb.field('xmin'), X1), pc.greater_equal(bb.field('xmax'), X0)), pc.and_(pc.less_equal(bb.field('ymin'), Y1), pc.greater_equal(bb.field('ymax'), Y0)))
        t = t.filter(m); bb = t.column('bbox').combine_chunks()
        return pa.table({'subtype': t.column('subtype'), 'class': t.column('class') if 'class' in t.column_names else pa.nulls(t.num_rows, pa.string()),
                         'lon': pc.divide(pc.add(bb.field('xmin'), bb.field('xmax')), 2), 'lat': pc.divide(pc.add(bb.field('ymin'), bb.field('ymax')), 2)})
    jobs = [(n, i) for n, h in res for i in h]
    with cf.ThreadPoolExecutor(12) as ex: T = pa.concat_tables(list(ex.map(get, jobs)))
    pq.write_table(T, out); print(out, T.num_rows, flush=True)
if __name__ == '__main__':
    run('divisions', 'division', '/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r22/ov/places_mp.parquet')
