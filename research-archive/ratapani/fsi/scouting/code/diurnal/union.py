import pandas as pd, numpy as np
P='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/papers_r7_diurnal/'
n=pd.read_parquet(P+'n20_aoi.parquet'); s=pd.read_parquet('/mnt/project-files/ratapani/viirs_snpp_2013_2024.parquet'); s['acq_date']=pd.to_datetime(s.acq_date)
m=pd.read_parquet(P+'modis_aoi.parquet')
def key(d,src):
    d=d[(d.acq_date.dt.year>=2018)&(d.acq_date.dt.year<=2024)]
    # local fire-day: night pass (01-03 IST) belongs to the previous afternoon's burn day -> use UTC date (night UTC ~20h of same date)
    return set(zip(d.acq_date.dt.strftime('%Y-%m-%d'),(d.latitude/0.0045).round().astype(int),(d.longitude/0.0049).round().astype(int)))
S=key(s,'s'); N=key(n,'n'); A=key(m[m.satellite=='Aqua'],'a'); T=key(m[m.satellite=='Terra'],'t')
U=S|N|A|T
print('cell-days SNPP',len(S),'N20',len(N),'union VIIRS',len(S|N),'gain over SNPP',round(len(S|N)/len(S)-1,3))
print('MODIS-only additions',len((A|T)-(S|N)),' Terra-only',len(T-(S|N|A)))
def nb(k,Sset):
    d,i,j=k
    return any((d,i+a,j+b) in Sset for a in (-1,0,1) for b in (-1,0,1))
Nnew=[k for k in N if not nb(k,S)]
print('N20 cell-days with no SNPP within 1 neighbour cell same date:',len(Nnew), 'gain', round(len(Nnew)/len(S),3))
Mnew=[k for k in (A|T) if not nb(k,S|N)]
print('MODIS cell-days with no VIIRS neighbour:',len(Mnew), round(len(Mnew)/len(S|N),3))
Tn=[k for k in T if not nb(k,S|N|A)]; print('Terra-only (morning) new:',len(Tn))
