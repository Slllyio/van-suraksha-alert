"""Holi eve split by satellite pass (night ~01:30 IST after the Holika Dahan bonfire evening; day ~13:30 IST).
Bootstrap over years and placebo shifts, all MP and by tribal share."""
import numpy as np, pandas as pd, calendar_dates as C
rng=np.random.default_rng(3)
s=pd.read_parquet('out/starts.parquet'); s['day']=s.bday
s['tribal']=s.Division.map(C.DIV_DIST).map(C.ST)>=30
def daily(sub):
    out=[]
    for y in range(2014,2027):
        days=pd.date_range(f'{y}-02-01',f'{y}-06-30'); n=sub[sub.season==y].groupby('day').size().reindex(days,fill_value=0).astype(float)
        out.append(pd.DataFrame({'year':y,'obs':n.values,'exp':((n.rolling(15,center=True).sum()-n)/14).values},index=days))
    t=pd.concat(out); md=t.index.strftime('%m%d'); return t[(md>='0215')&(md<='0615')]
H=[pd.Timestamp(h) for h in C.H['holi']]
rows=[]
for lab,sub in [('night pass, all MP',s[s.daynight=='N']),('day pass, all MP',s[s.daynight=='D']),
                ('night pass, tribal divisions',s[(s.daynight=='N')&s.tribal]),('night pass, other divisions',s[(s.daynight=='N')&~s.tribal])]:
    T=daily(sub)
    for k,kl in [(-1,'eve'),(0,'Holi day')]:
        x=T.loc[[h+pd.Timedelta(days=k) for h in H]]; rr=x.obs.sum()/x.exp.sum()
        idx=rng.integers(0,13,(4000,13)); rb=x.obs.values[idx].sum(1)/x.exp.values[idx].sum(1)
        null=[]
        for b in range(3000):
            dd=[h+pd.Timedelta(days=k+int(rng.choice(np.r_[-45:-3,4:46]))) for h in H]
            z=T.reindex(dd).dropna(); null.append(z.obs.sum()/z.exp.sum())
        null=np.log(null); p=(np.abs(null-np.median(null))>=abs(np.log(rr)-np.median(null))).mean()
        rows.append(dict(subset=lab,day=kl,obs=int(x.obs.sum()),exp=round(x.exp.sum(),1),RR=round(rr,3),lo=round(np.percentile(rb,2.5),3),hi=round(np.percentile(rb,97.5),3),
                         p_placebo=round(p,4),years_gt1=int((x.obs>x.exp).sum())))
R=pd.DataFrame(rows); print(R.to_string(index=False)); R.to_csv('out/holi_night_split.csv',index=False)
