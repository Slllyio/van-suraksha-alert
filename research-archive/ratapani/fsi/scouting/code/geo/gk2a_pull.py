# Pull GK2A AMI L1B full-disk SW038 + IR112 from the keyless NOAA AWS bucket, cut a central-India box, convert to BT, save npz per slot, delete source.
import sys, os, subprocess, datetime as dt, numpy as np, concurrent.futures as cf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h5c, threading
LOCK=threading.Lock()
from geos import ll2lc
OUT=sys.argv[1]; d0=dt.datetime.fromisoformat(sys.argv[2]); d1=dt.datetime.fromisoformat(sys.argv[3]); step=int(sys.argv[4]) if len(sys.argv)>4 else 30
TMP=OUT+'/tmp'; os.makedirs(TMP,exist_ok=True)
# box 21-25N 75-81E
ls,cs=[],[]
for la in (21,25):
    for lo in (75,81):
        l,c=ll2lc(la,lo); ls.append(l); cs.append(c)
L0,L1=int(min(ls))-5,int(max(ls))+6; C0,C1=int(min(cs))-5,int(max(cs))+6
c1,c2=1.191042e-5,1.4387752
def bt(path):
    f=h5c.fopen(path); a=h5c.attrs(f)
    dn,_=h5c.read(f,'image_pixel_values',(L0,C0),(L1-L0,C1-C0)); h5c.L.H5Fclose(f)
    dn=(dn & 0x3FFF).astype(np.float64); bad=dn>=16383
    R=a['DN_to_Radiance_Gain']*dn+a['DN_to_Radiance_Offset']; nu=1e4/float(a['channel_center_wavelength'])
    with np.errstate(all='ignore'):
        te=c2*nu/np.log(1+c1*nu**3/R)
    tb=a['Teff_to_Tbb_c0']+a['Teff_to_Tbb_c1']*te+a['Teff_to_Tbb_c2']*te**2
    tb[bad|(R<=0)]=np.nan; return tb.astype(np.float32), a['scene_acquisition_time']
def one(t):
    o=f'{OUT}/gk2a_{t:%Y%m%d%H%M}.npz'
    if os.path.exists(o): return 'skip'
    res={}
    for ch in ('sw038','ir112'):
        key=f'AMI/L1B/FD/{t:%Y%m}/{t:%d}/{t:%H}/gk2a_ami_le1b_{ch}_fd020ge_{t:%Y%m%d%H%M}.nc'; p=f'{TMP}/{ch}_{t:%Y%m%d%H%M}.nc'
        r=subprocess.run(['curl','-sS','-f','-m','180','-o',p,'https://noaa-gk2a-pds.s3.amazonaws.com/'+key],capture_output=True)
        if r.returncode!=0: return 'miss '+key
        try:
            with LOCK: res[ch],res[ch+'_time']=bt(p)
        finally: os.remove(p)
    np.savez_compressed(o,**res,L0=L0,C0=C0); return 'ok'
ts=[]; t=d0
while t<d1: ts.append(t); t+=dt.timedelta(minutes=step)
with cf.ThreadPoolExecutor(6) as ex:
    for t,r in zip(ts,ex.map(one,ts)):
        if r!='ok': print(t,r,flush=True)
print('done',len(ts),'box lines',L0,L1,'cols',C0,C1,flush=True)
