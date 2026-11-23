"""Details: per-year Holi and polling ratios, day/night split, single-day noise, Holi-anchoring of the season shape."""
import numpy as np, pandas as pd
import calendar_dates as C
from sklearn.linear_model import PoissonRegressor
from sklearn.preprocessing import SplineTransformer
rng=np.random.default_rng(7)
s=pd.read_parquet('out/starts.parquet'); s['day']=s.bday
YEARS=range(2014,2027)
# all-MP daily totals with 14-neighbour expectation
tot=[]
for y in YEARS:
    days=pd.date_range(f'{y}-02-01',f'{y}-06-30'); n=s[s.season==y].groupby('day').size().reindex(days,fill_value=0).astype(float)
    exp=(n.rolling(15,center=True).sum()-n)/14
    tot.append(pd.DataFrame({'year':y,'day':days,'obs':n.values,'exp':exp.values}))
T=pd.concat(tot); md=T.day.dt.strftime('%m%d'); T=T[(md>='0215')&(md<='0615')].set_index('day')
print('A. per-year Holi ratios (all MP, burning day)')
rows=[]
for h in C.H['holi']:
    h=pd.Timestamp(h); r={'year':h.year,'holi':h.date()}
    for k,lab in [(-1,'eve'),(0,'day'),(1,'p1'),(2,'p2')]:
        x=T.loc[h+pd.Timedelta(days=k)]; r[lab]=round(x.obs/x.exp,2)
    r['eve_obs']=int(T.loc[h-pd.Timedelta(days=1)].obs); r['season_starts']=int(T[T.year==h.year].obs.sum()); rows.append(r)
A=pd.DataFrame(rows); print(A.to_string(index=False)); A.to_csv('out/holi_by_year.csv',index=False)
print('years with eve>1:',(A.eve>1).sum(),'/13; day>1:',(A.day>1).sum(),'/13; eve+day mean ratio of logs:',round(np.exp(np.log(A[['eve','day']]).mean()).mean(),3))
# Holi eve+day pooled
ed=[pd.Timestamp(h)+pd.Timedelta(days=k) for h in C.H['holi'] for k in (-1,0)]
x=T.loc[ed]; print('eve+day pooled RR',round(x.obs.sum()/x.exp.sum(),3))
by=x.groupby('year')[['obs','exp']].sum(); idx=rng.integers(0,13,(4000,13)); rb=by.obs.values[idx].sum(1)/by.exp.values[idx].sum(1)
print('  CI',np.percentile(rb,[2.5,97.5]).round(3))
# noise: single random day per year summed over 13 years
v=[]
for b in range(4000):
    dd=[T[T.year==y].sample(1,random_state=int(rng.integers(1e9))).index[0] for y in YEARS]
    z=T.loc[dd]; v.append(z.obs.sum()/z.exp.sum())
v=np.array(v); print('B. null spread of a 13-year single-day RR: 2.5-97.5%',np.percentile(v,[2.5,97.5]).round(3),'sd log',np.log(v).std().round(3))
# day/night on Holi eve vs all
s['dn']=s.daynight
base=s[(s.day.dt.strftime('%m%d')>='0215')&(s.day.dt.strftime('%m%d')<='0615')]
he=s[s.day.isin([pd.Timestamp(h)-pd.Timedelta(days=1) for h in C.H['holi']])]
hd=s[s.day.isin([pd.Timestamp(h) for h in C.H['holi']])]
print('C. night share: season',round((base.dn=='N').mean(),3),'Holi eve',round((he.dn=='N').mean(),3),'Holi day',round((hd.dn=='N').mean(),3))
print('   median FRP: season',base.frp.median(),'eve',he.frp.median(),'day',hd.frp.median())
print('   nonforest-VTM share: season',round(base.nonforest.mean(),3),'eve',round(he.nonforest.mean(),3))
# night-only RR on eve (01:30 pass after Holika Dahan)
for lab,sub in [('night',s[s.dn=='N']),('day',s[s.dn=='D'])]:
    o=e=0
    for h in C.H['holi']:
        for k in (-1,0):
            y=pd.Timestamp(h).year; d=pd.Timestamp(h)+pd.Timedelta(days=k)
            days=pd.date_range(d-pd.Timedelta(days=7),d+pd.Timedelta(days=7)); n=sub[sub.season==y].groupby('day').size().reindex(days,fill_value=0)
            if k==-1: o1=n.loc[d]; e1=(n.sum()-n.loc[d])/14; print(f'   {lab} pass, Holi eve {y}: {o1} vs {e1:.1f}') if False else None
            if k==-1: o+=n.loc[d]; e+=(n.sum()-n.loc[d])/14
    print(f'   {lab}-pass starts on Holi eve: RR {o/e:.3f} ({o} vs {e:.1f})')
# D. polling per election
s['dist']=s.Division.map(C.DIV_DIST); s['seat']=s.dist.map(C.DIST_SEAT)
print('D. polling own-seat by election')
for y,ph in C.LS.items():
    o=e=0
    for d,seats in ph.items():
        d=pd.Timestamp(d); days=pd.date_range(d-pd.Timedelta(days=7),d+pd.Timedelta(days=7))
        sub=s[(s.season==y)&s.seat.isin(seats.split())]
        n=sub.groupby('day').size().reindex(days,fill_value=0); o+=n.loc[d]; e+=(n.sum()-n.loc[d])/14
        print(f'   {d.date()} {seats[:40]:40s} obs {n.loc[d]:4d} exp {(n.sum()-n.loc[d])/14:6.1f}')
    print(f'  {y}: RR {o/e:.2f}')
# E. Is the season shape anchored to Holi? Poisson: year FE + DOY spline + weeks-since-Holi bins
T2=T.reset_index(); T2['doy']=T2.day.dt.dayofyear
hol={pd.Timestamp(h).year:pd.Timestamp(h) for h in C.H['holi']}
T2['dsh']=(T2.day-T2.year.map(hol)).dt.days
bins=list(range(-21,43,7)); T2['wk']=pd.cut(T2.dsh,bins=[-999]+bins+[999],right=False,labels=False)
def fit(df):
    sp=SplineTransformer(n_knots=6,degree=3).fit_transform(df[['doy']])
    yr=pd.get_dummies(df.year,drop_first=True).values
    wk=pd.get_dummies(df.wk).values; wk=np.delete(wk,0,axis=1)  # reference = more than 21 d before Holi
    X=np.hstack([sp,yr,wk]).astype(float)
    m=PoissonRegressor(alpha=1e-6,max_iter=3000).fit(X,df.obs.values)
    return m.coef_[-wk.shape[1]:]
c0=fit(T2); B=[]
for b in range(200):
    ys=rng.choice(list(YEARS),13); d=pd.concat([T2[T2.year==y].assign(year=1000+i if False else y*100+i) for i,y in enumerate(ys)])
    B.append(fit(d))
B=np.array(B); lab=[f'[{a},{a+7})' for a in bins[:-1]]+['>=42']
E=pd.DataFrame({'weeks_since_holi_bin':lab[:len(c0)],'RR':np.exp(c0),'lo':np.exp(np.percentile(B,2.5,0)),'hi':np.exp(np.percentile(B,97.5,0))})
print('E. Holi-anchored season effect (vs >21 d before Holi), controlling DOY spline + year FE'); print(E.round(3).to_string(index=False)); E.to_csv('out/holi_anchor.csv',index=False)
# F. season median start date vs Holi date
F=pd.DataFrame({'year':list(YEARS)}); F['holi_doy']=F.year.map(lambda y:hol[y].dayofyear)
F['med_doy']=F.year.map(lambda y:s[(s.season==y)&(s.day.dt.strftime('%m%d')>='0215')&(s.day.dt.strftime('%m%d')<='0615')].day.dt.dayofyear.median())
from scipy.stats import spearmanr, linregress
lr=linregress(F.holi_doy,F.med_doy); print('F. median start DOY vs Holi DOY: slope',round(lr.slope,2),'r',round(lr.rvalue,2),'p',round(lr.pvalue,3)); print(F.to_string(index=False))
F.to_csv('out/season_median_vs_holi.csv',index=False)
