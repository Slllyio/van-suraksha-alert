import numpy as np
rng=np.random.default_rng(0); N=200000
def run(mu_ign, sd_ign, med_dur, sdlog=0.8):
    ig=rng.normal(mu_ign,sd_ign,N)            # ignition hour (local)
    dur=np.exp(np.log(med_dur)+sdlog*rng.standard_normal(N))
    end=ig+dur
    def active(t):  # pass at hour t on day0 or t+24
        return ((ig<=t)&(end>=t))|((ig<=t+24)&(end>=t+24))
    day=active(13.5); night=active(25.5)  # 01:30 next day
    terra=active(11.0); aqua=active(13.67)
    seen=day|night
    nd=night.sum(); dd=day.sum()
    return dict(mu=mu_ign,sd=sd_ign,dur=med_dur,miss=round(1-seen.mean(),2),night_share=round(nd/(nd+dd),2),
                night_no_day=round((night&~day).sum()/nd,2), terra_seen_by_aqua=round((terra&aqua).sum()/max(terra.sum(),1),2),
                aqua_pre_terra=round((terra&aqua).sum()/max(aqua.sum(),1),2), aqua_frac=round(aqua.sum()/(aqua.sum()+terra.sum()),2))
for mu in [11,12,13,14]:
  for sd in [1.5,2.5]:
    for d in [2,4,8]:
        print(run(mu,sd,d))
