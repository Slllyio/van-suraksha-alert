import json, requests, io, numpy as np
from PIL import Image, ImageDraw
import math
def tile(z,x,y):
    for _ in range(5):
        r=requests.get(f'https://services.arcgisonline.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',timeout=60)
        if r.headers.get('content-type','').startswith('image'): return Image.open(io.BytesIO(r.content)).convert('RGB')
    return Image.new('RGB',(256,256),'gray')
def chip(lon,lat,z=18):
    n=2**z; fx=(lon+180)/360*n; fy=(1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n
    tx,ty=int(fx),int(fy); big=Image.new('RGB',(768,768))
    for i in range(3):
        for j in range(3): big.paste(tile(z,tx-1+i,ty-1+j),(i*256,j*256))
    px,py=int((fx-tx+1)*256),int((fy-ty+1)*256)
    return big.crop((px-200,py-200,px+200,py+200))
pts = json.load(open('vhr/pts.json')); rng = np.random.default_rng(1)
for k in range(1, 6):
    cand = [p for p in pts if p['cls'] == k and p.get('date', '')[5:7] in ('02', '03', '04')]
    cand = cand[:6]
    sheet = Image.new('RGB', (3 * 400, 2 * 420), 'white'); d = ImageDraw.Draw(sheet)
    for i, p in enumerate(cand):
        im = chip(p['lon'], p['lat']); dd = ImageDraw.Draw(im); dd.rectangle([200 - 9, 200 - 9, 200 + 9, 200 + 9], outline='red', width=2)
        x, y = (i % 3) * 400, (i // 3) * 420; sheet.paste(im, (x, y + 20)); d.text((x + 5, y + 4), f"#{i} {p['date']} {p['lat']:.4f},{p['lon']:.4f}", fill='black')
        p['sheet_idx'] = i
    sheet.save(f'vhr/class{k}.jpg', quality=85); print(k, len(cand))
json.dump(pts, open('vhr/pts.json', 'w'))
