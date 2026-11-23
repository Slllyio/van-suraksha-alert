# fetch Bhuvan WMS layers as georeferenced PNG tiles -> mosaic GeoTIFF (EPSG:4326)
import sys, os, subprocess, numpy as np, rasterio
from rasterio.transform import from_origin
from PIL import Image
D='/tmp/claude-0/-home-user/be9b8f54-cc26-52cb-bdbb-9c8008a24baf/scratchpad/r9_barrier_data/bhuvan/'
layers=sys.argv[1:]
x0,x1,y0,y1=77.4,78.3,22.7,23.3; st=0.1; px=1000  # 0.0001 deg ~ 10.2 m
nx=int(round((x1-x0)/st)); ny=int(round((y1-y0)/st))
for L in layers:
    tag=L.replace(':','_'); os.makedirs(D+tag,exist_ok=True)
    out=np.zeros((ny*px,nx*px,4),np.uint8)
    for i in range(nx):
        for j in range(ny):
            bx=(x0+i*st,y1-(j+1)*st,x0+(i+1)*st,y1-j*st); f=D+tag+f'/t{i}_{j}.png'
            if not os.path.exists(f) or os.path.getsize(f)<200:
                url=("https://bhuvan-vec1.nrsc.gov.in/bhuvan/wms?service=WMS&version=1.1.1&request=GetMap&layers=%s&styles=&srs=EPSG:4326&bbox=%.4f,%.4f,%.4f,%.4f&width=%d&height=%d&format=image/png&transparent=true"%(L,*bx,px,px))
                for a in range(4):
                    subprocess.run(['curl','-sS','-m','120','-o',f,url])
                    try: Image.open(f).verify(); break
                    except Exception: pass
            try: out[j*px:(j+1)*px,i*px:(i+1)*px]=np.array(Image.open(f).convert('RGBA'))
            except Exception as e: print('fail',L,i,j)
    tr=from_origin(x0,y1,st/px,st/px)
    with rasterio.open(D+tag+'.tif','w',driver='GTiff',height=out.shape[0],width=out.shape[1],count=4,dtype='uint8',crs='EPSG:4326',transform=tr,compress='deflate') as o:
        o.write(np.moveaxis(out,2,0))
    print(L,'alpha>0 frac',(out[...,3]>0).mean())
