import pandas as pd, sys
r=pd.read_csv(sys.argv[1]); r['hit']=r.hit.map({True:1,False:0,'True':1,'False':0}).astype(float)
if 'hit_s' in r: r['hit_s']=r.hit_s.map({True:1,False:0,'True':1,'False':0}).astype(float)
else: r['hit_s']=float('nan')
V=r[r.viirs.notna()&r.pbase.notna()&(r.n_inside>0)]
print('VIIRS-dated bins with >=1 S3 look inside window:',len(V))
for lab,sub in [('all',V),('snr>2',V[V.snr>2]),('snr>3',V[V.snr>3]),('bfrac<0.3',V[V.bfrac<0.3]),('bfrac>=0.5',V[V.bfrac>=0.5]),('bfrac>=0.5&snr>2',V[(V.bfrac>=0.5)&(V.snr>2)])]:
    if len(sub): print(f'  {lab}: n={len(sub)} S3 hit={sub.hit.mean():.3f} (strict {sub.hit_s.mean():.3f}) uniform baseline={sub.pbase.mean():.3f} lift={sub.hit.mean()/sub.pbase.mean():.2f}x; median new interval {sub.newlen.median():.2f} d (window {sub.L.median():.1f} d); mean new/old {(sub.newlen/sub.L).mean():.2f}')
