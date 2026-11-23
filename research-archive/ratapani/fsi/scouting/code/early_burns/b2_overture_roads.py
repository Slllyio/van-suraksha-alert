"""Fetch Overture transportation segments (roads) for the MP bbox via HTTP range reads of row groups whose bbox stats intersect MP.
No keys needed. Output: roads_mp.parquet (WKB geometry, class)."""
import requests, io, re, pyarrow.parquet as pq, pyarrow as pa, sys, concurrent.futures as cf
B='https://overturemapswestus2.blob.core.windows.net/release'
REL='2026-09-23.0'; X0,X1,Y0,Y1=74.0,82.9,21.0,26.9
S=requests.Session()
class HF(io.RawIOBase):
    def __init__(s,u):
        s.u=u; s.p=0; s.n=int(S.head(u).headers['Content-Length'])
    def seekable(s): return True
    def readable(s): return True
    def tell(s): return s.p
    def seek(s,o,w=0):
        s.p = o if w==0 else (s.p+o if w==1 else s.n+o); return s.p
    def read(s,k=-1):
        if k is None or k<0: k=s.n-s.p
        if k==0 or s.p>=s.n: return b''
        e=min(s.p+k,s.n)-1
        for t in range(5):
            try:
                r=S.get(s.u,headers={'Range':f'bytes={s.p}-{e}'},timeout=120); r.raise_for_status(); break
            except Exception as ex:
                if t==4: raise
        b=r.content; s.p+=len(b); return b
    def readinto(s,b):
        d=s.read(len(b)); b[:len(d)]=d; return len(d)
x=S.get(B,params={'restype':'container','comp':'list','prefix':f'{REL}/theme=transportation/type=segment/'}).text
names=re.findall('<Name>([^<]*)</Name>',x)
def rg_hits(name):
    f=pq.ParquetFile(HF(f'{B}/{name}'))
    md=f.metadata; sch=f.schema_arrow.names
    cols={md.row_group(0).column(j).path_in_schema:j for j in range(md.row_group(0).num_columns)}
    ix={k:cols[f'bbox.{k}'] for k in ['xmin','xmax','ymin','ymax']}
    hits=[]
    for i in range(md.num_row_groups):
        rg=md.row_group(i); st={k:rg.column(j).statistics for k,j in ix.items()}
        if st['xmin'].min<=X1 and st['xmax'].max>=X0 and st['ymin'].min<=Y1 and st['ymax'].max>=Y0: hits.append(i)
    return name,hits
with cf.ThreadPoolExecutor(16) as ex: res=list(ex.map(rg_hits,names))
res=[r for r in res if r[1]]
print('files with hits',len(res),'row groups',sum(len(h) for _,h in res),flush=True)
out=[]
def get(nh):
    name,i=nh
    f=pq.ParquetFile(HF(f'{B}/{name}'))
    t=f.read_row_group(i,columns=['subtype','class','bbox','geometry'])
    bb=t.column('bbox').combine_chunks()
    import pyarrow.compute as pc
    m=pc.and_(pc.and_(pc.less_equal(bb.field('xmin'),X1),pc.greater_equal(bb.field('xmax'),X0)),pc.and_(pc.less_equal(bb.field('ymin'),Y1),pc.greater_equal(bb.field('ymax'),Y0)))
    m=pc.and_(m,pc.equal(t.column('subtype'),'road'))
    return t.filter(m).select(['class','geometry'])
jobs=[(n,i) for n,h in res for i in h]
with cf.ThreadPoolExecutor(12) as ex:
    for k,t in enumerate(ex.map(get,jobs)):
        out.append(t); print(k,len(jobs),t.num_rows,flush=True)
T=pa.concat_tables(out); pq.write_table(T,'/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r15_firms_nd/roads_mp.parquet')
print(T.num_rows)
