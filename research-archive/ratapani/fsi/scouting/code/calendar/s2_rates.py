"""Calendar rate ratios for first-day fire starts, all MP, S-NPP, 2014-2026, 15 Feb-15 Jun.
Expected count for stratum s, day d = mean of the 14 neighbouring days (d-7..d+7 excluding d) in the same stratum-year.
RR = sum(obs)/sum(exp) over event days. CI: bootstrap over years (B=4000). Placebo p: event dates shifted by a common
random offset per year (|k| in 4..45 days), 4000 draws. Holm correction over the main family.
Usage: python3 s2_rates.py [bday|cday] [all|forest]"""
import sys, numpy as np, pandas as pd
import calendar_dates as C
DAYCOL=sys.argv[1] if len(sys.argv)>1 else 'bday'; SUB=sys.argv[2] if len(sys.argv)>2 else 'all'
rng=np.random.default_rng(15)
s=pd.read_parquet('out/starts.parquet')
if SUB=='forest': s=s[~s.nonforest]
s['day']=s[DAYCOL]
typ=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/code/mp_types/out/division_types_final.csv')[['Division','dominant']]
grp=dict(zip(typ.Division,typ.dominant.replace({'bamboo':'moist_mixed'})))
s['grp']=s.Division.map(grp)
s['dist']=s.Division.map(C.DIV_DIST); s['st']=s.dist.map(C.ST); s['seat']=s.dist.map(C.DIST_SEAT)
s['tribal']=np.where(s.st>=30,'tribal','other')
YEARS=list(range(2014,2027))
def table(key):
    """daily obs and exp per stratum-year, 1 Feb-30 Jun, then cut to 15 Feb-15 Jun."""
    out=[]
    for y in YEARS:
        days=pd.date_range(f'{y}-02-01',f'{y}-06-30')
        sy=s[s.season==y]
        c=sy.groupby([key,'day']).size()
        for k in sorted(s[key].dropna().unique()):
            n=c.get(k,pd.Series(dtype=float)).reindex(days,fill_value=0).astype(float) if k in c.index.get_level_values(0) else pd.Series(0.0,index=days)
            roll=n.rolling(15,center=True).sum()
            exp=(roll-n)/14
            out.append(pd.DataFrame({'stratum':k,'year':y,'day':days,'obs':n.values,'exp':exp.values}))
    t=pd.concat(out); md=t.day.dt.strftime('%m%d'); t=t[(md>='0215')&(md<='0615')]
    return t.reset_index(drop=True)
def rr_by_year(t,mask):
    a=t[mask].groupby('year')[['obs','exp']].sum().reindex(YEARS,fill_value=0); return a
def boot(a,B=4000):
    o=a.obs.values; e=a.exp.values; ok=e>0
    o,e=o[ok],e[ok]; n=len(o)
    if n==0: return np.nan,np.nan,np.nan,np.nan,0
    idx=rng.integers(0,n,(B,n)); rb=o[idx].sum(1)/e[idx].sum(1)
    rr=o.sum()/e.sum(); p=min(1,2*min((rb<=1).mean(),(rb>=1).mean()))
    return rr,np.percentile(rb,2.5),np.percentile(rb,97.5),p,n
def event_mask(t,dates,offs):
    dd=set()
    for x in dates:
        for k in offs: dd.add(pd.Timestamp(x)+pd.Timedelta(days=k))
    return t.day.isin(dd)
def placebo(t,dates,offs,rr,B=4000):
    dates=pd.to_datetime(dates); yrs=dates.year
    tt=t.groupby('day')[['obs','exp']].sum()  # sum over strata (common shift keeps the spatial pattern)
    vals=[]
    for b in range(B):
        k={y:rng.choice(np.r_[-45:-3,4:46]) for y in YEARS}
        dd=[d+pd.Timedelta(days=int(k[y])+o) for d,y in zip(dates,yrs) for o in offs]
        sub=tt.reindex(dd).dropna()
        if sub.exp.sum()>0: vals.append(sub.obs.sum()/sub.exp.sum())
    v=np.log(np.array(vals)); return ((np.abs(v-np.median(v))>=abs(np.log(rr)-np.median(v))).mean())
EV=[('Holi eve (Holika Dahan)','holi',[-1]),('Holi day','holi',[0]),('Holi +1..+2','holi',[1,2]),('Holi +3..+4','holi',[3,4]),
    ('Mahashivratri','shivratri',[0]),('Gudi Padwa / Chaitra Pratipada','gudi_padwa',[0]),('Ram Navami','ram_navami',[0]),
    ('Akshaya Tritiya','akshaya_tritiya',[0]),('Akshaya Tritiya +1..+7','akshaya_tritiya',list(range(1,8))),
    ('Eid (Fitr 2019-26, Adha 2025-26)','eid',[0]),('MPBSE class-12 exams end +1..+3','exam_end',[1,2,3]),
    ('IPL final day (null)','ipl_final',[0]),('IPL final +1 (null)','ipl_final',[1])]
rows=[]
G=table('grp')
for name,key,offs in EV:
    m=event_mask(G,C.H[key],offs); a=rr_by_year(G,m); rr,lo,hi,p,n=boot(a)
    pp=placebo(G,C.H[key],offs,rr)
    rows.append(dict(effect=name,obs=a.obs.sum(),exp=round(a.exp.sum(),1),RR=rr,lo=lo,hi=hi,p_boot=p,p_placebo=pp,years=n))
# polling days: own seat polls (stratum = seat)
S=table('seat')
pm=np.zeros(len(S),bool); pmo=np.zeros(len(S),bool); pdates=[]
for y,ph in C.LS.items():
    for d,seats in ph.items():
        pdates.append(d); sd=S.day==pd.Timestamp(d); own=S.stratum.isin(seats.split())
        pm|=sd&own; pmo|=sd&~own
# bootstrap over seat-years (29 seats x 3 elections) because 3 years is too few to resample
for name,m in [('Polling day, own Lok Sabha seat',pm),('Polling day, other seats (same date)',pmo)]:
    a=S[m].groupby(['stratum','year'])[['obs','exp']].sum()
    rr,lo,hi,p,n=boot(a)
    pp=placebo(S,pdates,[0],rr) if 'own' in name else np.nan
    rows.append(dict(effect=name,obs=a.obs.sum(),exp=round(a.exp.sum(),1),RR=rr,lo=lo,hi=hi,p_boot=p,p_placebo=pp,years=n))
# weekdays
for w,wn in enumerate(['Mon','Tue','Wed','Thu','Fri','Sat','Sun']):
    m=G.day.dt.weekday==w; a=rr_by_year(G,m); rr,lo,hi,p,n=boot(a)
    rows.append(dict(effect='Weekday '+wn,obs=a.obs.sum(),exp=round(a.exp.sum(),1),RR=rr,lo=lo,hi=hi,p_boot=p,p_placebo=np.nan,years=n))
R=pd.DataFrame(rows)
R['p_use']=R[['p_boot','p_placebo']].max(axis=1)
# Holm
o=np.argsort(R.p_use.values); m=len(R); adj=np.empty(m); run=0
for i,j in enumerate(o): run=max(run,min(1,(m-i)*R.p_use.values[j])); adj[j]=run
R['p_holm']=adj
R['robust_1.3x']=((R.RR>=1.3)|(R.RR<=1/1.3))&(R.p_holm<0.05)&((R.lo>1)|(R.hi<1))
pd.set_option('display.width',250)
print(DAYCOL,SUB,'starts in window:',int(G.obs.sum()))
print(R.round(3).to_string(index=False))
R.round(4).to_csv(f'out/rr_{DAYCOL}_{SUB}.csv',index=False)
# tribal split
T=table('tribal'); rows=[]
for name,key,offs in EV[:9]+[EV[11]]:
    m=event_mask(T,C.H[key],offs)
    at=rr_by_year(T,m&(T.stratum=='tribal')); ao=rr_by_year(T,m&(T.stratum=='other'))
    ot,et,oo,eo=at.obs.values,at.exp.values,ao.obs.values,ao.exp.values
    idx=rng.integers(0,13,(4000,13))
    rt=ot[idx].sum(1)/et[idx].sum(1); ro=oo[idx].sum(1)/eo[idx].sum(1); d=rt/ro
    rows.append(dict(effect=name,RR_tribal=ot.sum()/et.sum(),RR_other=oo.sum()/eo.sum(),ratio=(ot.sum()/et.sum())/(oo.sum()/eo.sum()),
        lo=np.nanpercentile(d,2.5),hi=np.nanpercentile(d,97.5),n_tribal=int(ot.sum()),n_other=int(oo.sum())))
for w,wn in [(6,'Sunday')]:
    m=T.day.dt.weekday==w
    at=rr_by_year(T,m&(T.stratum=='tribal')); ao=rr_by_year(T,m&(T.stratum=='other'))
    rows.append(dict(effect=wn,RR_tribal=at.obs.sum()/at.exp.sum(),RR_other=ao.obs.sum()/ao.exp.sum(),ratio=np.nan,lo=np.nan,hi=np.nan,n_tribal=int(at.obs.sum()),n_other=int(ao.obs.sum())))
TR=pd.DataFrame(rows); print(TR.round(3).to_string(index=False)); TR.round(4).to_csv(f'out/tribal_{DAYCOL}_{SUB}.csv',index=False)
import sys as _s; _s.stdout.flush(); print('share of starts in tribal (ST>=30%) divisions:',round(T[T.stratum=='tribal'].obs.sum()/T.obs.sum(),3))
