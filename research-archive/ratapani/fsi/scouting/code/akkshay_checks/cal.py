import pandas as pd, numpy as np
from scipy.stats import chisquare
ig=pd.read_csv('/mnt/project-files/ratapani/fsi/scouting/data/ignition_points.csv')
ig=ig[(ig.event_role=='first_day_of_fire')&(ig.status=='ok')].copy()
ig['t']=pd.to_datetime(ig.t_ign_med_ist); ig['d']=ig.t.dt.normalize()
md=ig.d.dt.strftime('%m%d'); ig=ig[(md>='0215')&(md<='0615')]
print('ignitions',len(ig))
# weekday, detrended: compare each day's count with the mean of +/-3 days same season (removes seasonal curve)
days=pd.DataFrame({'d':pd.date_range('2017-01-01','2026-06-30')}); days['md']=days.d.dt.strftime('%m%d'); days=days[(days.md>='0215')&(days.md<='0615')]
c=ig.groupby('d').size(); days['n']=days.d.map(c).fillna(0)
days['yr']=days.d.dt.year
days['smooth']=days.groupby('yr').n.transform(lambda s:s.rolling(15,center=True,min_periods=5).mean())
days['wd']=days.d.dt.day_name()
w=days.groupby('wd').agg(obs=('n','sum'),exp=('smooth','sum')); w['ratio']=(w.obs/w.exp).round(3)
w=w.reindex(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']); print(w)
print('chi2 p',chisquare(w.obs,w.exp/w.exp.sum()*w.obs.sum()).pvalue)
holi=pd.to_datetime(['2017-03-13','2018-03-02','2019-03-21','2020-03-10','2021-03-29','2022-03-18','2023-03-08','2024-03-25','2025-03-14','2026-03-04'])
rows=[]
for h in holi:
    for k in range(-5,6):
        r=days[days.d==h+pd.Timedelta(days=k)]
        if len(r): rows.append(dict(k=k,obs=r.n.iloc[0],exp=r.smooth.iloc[0]))
H=pd.DataFrame(rows).groupby('k').sum(); H['ratio']=(H.obs/H.exp).round(2); print('days from Holi (Holika dahan is the evening before)'); print(H)
# bootstrap noise level for a single-day ratio summed over 10 years
print('typical single-day ratio sd (random days):',round(np.std([ (lambda s: s.n.sum()/s.smooth.sum())(days.sample(10,random_state=i)) for i in range(500)]),2))
days.to_csv('cal_days.csv',index=False)
