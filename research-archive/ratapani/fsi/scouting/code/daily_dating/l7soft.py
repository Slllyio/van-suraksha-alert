"""Landsat-7 splits of 20 m burn windows: is the cell's scar already visible (scar-minus-ring NBR drop) at an L7 look inside the window?
Writes ../r9data/l7soft_<year>.csv with cut_lo/cut_hi (IST day-of-year) per (cell, s, e)."""
import sys, os, glob, numpy as np, pandas as pd
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__))); from common import *
year=int(sys.argv[1]); D=sys.argv[2]
px,a,T,cr=windows_px(year); unb=(a[0]==-999)
sc=[]
for fn in glob.glob(f'{D}/*.npz'):
    try:
        z=np.load(fn)
        if 'empty' in z: continue
        d=pd.Timestamp(str(z['date']))
    except Exception: continue
    doy=(d-pd.Timestamp(f'{year}-01-01')).days
    if -80<=doy<=200: sc.append((doy,fn))
sc.sort(); cache={}
def get(fn):
    if fn not in cache: cache[fn]=np.load(fn)['nbr']
    return cache[fn]
print(year,'L7 scenes',len(sc),flush=True)
def contrast(n,P,box):
    pv=n[P[0],P[1]]; pv=pv[pv>-32768]
    if len(pv)<max(20,0.3*P[0].size): return np.nan
    r0,r1,c0,c1=box; sub=n[r0:r1,c0:c1]; m=unb[r0:r1,c0:c1]&(sub>-32768)
    if m.sum()<100: return np.nan
    return (np.median(pv)-np.median(sub[m]))/10000
rows=[]
docs=np.array([s[0] for s in sc])
for (cid,s,e),grp in px.groupby(['cell_id','s','e']):
    inside=[k for k,(dy,fn) in enumerate(sc) if s<dy<e]
    if not inside: continue
    P=(grp.r.values,grp.c.values); box=(max(P[0].min()-25,0),P[0].max()+26,max(P[1].min()-25,0),P[1].max()+26)
    mag=np.median(grp.mag.values)/1000
    cpre=np.nan
    for k in [k for k,(dy,fn) in enumerate(sc) if s-48<=dy<=s][::-1]:
        cpre=contrast(get(sc[k][1]),P,box)
        if np.isfinite(cpre): break
    cpost=np.nan
    for k in [k for k,(dy,fn) in enumerate(sc) if e<=dy<=e+32]:
        cpost=contrast(get(sc[k][1]),P,box)
        if np.isfinite(cpost): break
    lo,hi=s+10.7/24,e+10.7/24; dec=[]
    for k in inside:
        ct=contrast(get(sc[k][1]),P,box)
        if not np.isfinite(ct): continue
        if np.isfinite(cpre): b=(cpre-ct)>0.5*mag
        elif np.isfinite(cpost): b=(ct-cpost)<0.5*mag
        else: continue
        dec.append((sc[k][0]+10.2/24,b,ct))
    if not dec: rows.append(dict(season=year,cell_id=cid,s=s,e=e,n_l7=len(inside),decided=0)); continue
    first_b=[t for t,b,_ in dec if b]
    if first_b: hi=first_b[0]; lo=max([lo]+[t for t,b,_ in dec if (not b) and t<hi])
    else: lo=max(t for t,b,_ in dec)
    rows.append(dict(season=year,cell_id=cid,s=s,e=e,n_l7=len(inside),decided=len(dec),has_pre=np.isfinite(cpre),has_post=np.isfinite(cpost),mag=mag,cut_lo=lo,cut_hi=hi,
                     consistent=all(b for t,b,_ in dec if t>=hi) and not any(b for t,b,_ in dec if t<hi)))
    if len(cache)>60: cache.clear()
out=pd.DataFrame(rows); out.to_csv(f'../r9data/l7soft_{year}.csv',index=False)
print(year,'windows with L7 inside',len(out),'decided',(out.decided>0).sum(),flush=True)
