import numpy as np
from scipy import ndimage
from PIL import Image
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/'
R=np.load(D+'recurrent_edges_5_0.5.npz'); m=R['m_all']; C=R['C_all']
LZ=dict(np.load(D+'layers20.npz')); LZ.update(dict(np.load(D+'layers20_extra.npz')))
print('recurrent km',m.sum()*0.02)
for k in ['ms_roads','ov_osm_roads','ov_tomtom','mmi_roads','bh_drain','mmi_hydro','stream_0.25km2','stream_1km2','ridge_100c','fedge']:
    d=ndimage.distance_transform_edt(~LZ[k+'_m'],sampling=20)
    # share of recurrent px within 40 m, vs share of all burnable px within 40 m
    z=np.load('/mnt/project-files/ratapani/spread/data_shared/grid20.npz'); bur=np.isin(z['wc'],[10,20,30])
    print(f'{k:15s} recurrent within 40 m: {(d[m]<=40).mean():.3f}   burnable land within 40 m: {(d[bur]<=40).mean():.3f}')
# straightness: per component, end-to-end / pixel length
lab,n=ndimage.label(m,np.ones((3,3)))
sizes=np.bincount(lab.ravel())[1:]
objs=ndimage.find_objects(lab)
st=[]
for i,sl in enumerate(objs):
    if sizes[i]<15: continue
    rr,cc=np.nonzero(lab[sl]==i+1)
    ext=np.hypot(rr.max()-rr.min(),cc.max()-cc.min())
    st.append((sizes[i],ext/sizes[i]))
st=np.array(st); print('components>=300 m:',len(st),'median straightness (bbox diag / length)',np.median(st[:,1]).round(2),'share >0.8:',(st[:,1]>0.8).mean().round(2))
# image of a 8x8 km window in the sanctuary core
r0,c0=900,1600; h=400
img=np.zeros((h,h,3),np.uint8)+255
cc=np.clip(C[r0:r0+h,c0:c0+h]*25,0,200).astype(np.uint8); img[...,0]-=cc; img[...,1]-=cc  # blue-ish = how often an edge
for k,col in [('bh_drain',(0,150,255)),('ms_roads',(200,100,0))]:
    mm=ndimage.binary_dilation(LZ[k+'_m'][r0:r0+h,c0:c0+h]); img[mm]=col
img[m[r0:r0+h,c0:c0+h]]=(220,0,0)
Image.fromarray(img).resize((800,800),Image.NEAREST).save(D+'recur_window.png')
