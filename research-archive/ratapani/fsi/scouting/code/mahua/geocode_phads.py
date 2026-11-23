"""Match phad (village) names from the MFP Federation 2026 phad list to OSM place nodes by phonetic skeleton,
anchored on the society village. Output out/phads_geocoded.csv."""
import json, re, difflib, numpy as np, pandas as pd, unicodedata
V={'अ':'a','आ':'a','इ':'i','ई':'i','उ':'u','ऊ':'u','ए':'e','ऐ':'ai','ओ':'o','औ':'au','ऋ':'ri'}
M={'ा':'a','ि':'i','ी':'i','ु':'u','ू':'u','े':'e','ै':'ai','ो':'o','ौ':'au','ृ':'ri','ं':'n','ँ':'n','ः':'','ॅ':'e','ॉ':'o'}
C={'R':'r','क':'k','ख':'kh','ग':'g','घ':'gh','ङ':'n','च':'ch','छ':'chh','ज':'j','झ':'jh','ञ':'n','ट':'t','ठ':'th','ड':'d','ढ':'dh','ण':'n',
'त':'t','थ':'th','द':'d','ध':'dh','न':'n','प':'p','फ':'ph','ब':'b','भ':'bh','म':'m','य':'y','र':'r','ल':'l','ळ':'l','व':'v','श':'sh','ष':'sh','स':'s','ह':'h'}
def roman(s):
    s=unicodedata.normalize('NFC',s).replace('ड़','R').replace('ढ़','R').replace('ड़','R').replace('ढ़','R').replace('़','')
    out=[];i=0
    while i<len(s):
        ch=s[i]
        if ch in C:
            out.append(C[ch]); nx=s[i+1] if i+1<len(s) else ''
            if nx=='्': i+=2; continue
            if nx in M: out.append(M[nx]); i+=2; continue
            out.append('a'); i+=1; continue
        if ch in V: out.append(V[ch])
        elif ch in M: out.append(M[ch])
        elif ch==' ': out.append(' ')
        i+=1
    r=''.join(out)
    r=re.sub(r'a\b','',r)  # final schwa
    return r
def skel(r):
    r=r.lower(); r=re.sub(r'(khurd|kalan|kala|kanla|khurad|kh\.|kalam)\b','',r)
    r=r.replace('w','v').replace('v','b').replace('sh','s').replace('ph','f').replace('z','j').replace('q','k').replace('x','ks')
    r=re.sub(r'(?<=[bcdfgjklmnprstvy])h','',r); r=re.sub(r'^h','h',r)
    r=re.sub(r'[aeiou ]','',r); r=re.sub(r'(.)\1+',r'\1',r)
    return r
J=json.load(open('out/osm_places.json'))['elements']
P=pd.DataFrame([dict(name=e['tags'].get('name'),hi=e['tags'].get('name:hi'),lat=e['lat'],lon=e['lon'],place=e['tags'].get('place')) for e in J if 'name' in e['tags']])
P['sk']=P.name.map(skel)
d=pd.read_csv('out/phads_ratapani_unions.csv')
d['rom']=d.phad_u.map(roman); d['sk']=d.rom.map(skel); d['soc_rom']=d.society_u.map(roman); d['soc_sk']=d.soc_rom.map(skel)
def cand(sk,full,sub=None):
    Q=P if sub is None else sub
    sc=Q.sk.map(lambda x: difflib.SequenceMatcher(None,sk,x).ratio())
    full_sc=Q.name.str.lower().map(lambda x: difflib.SequenceMatcher(None,full.lower(),x).ratio())
    s=0.6*sc+0.4*full_sc
    return Q.assign(score=s).sort_values('score',ascending=False)
def hav(lat1,lon1,lat2,lon2):
    p=np.pi/180; a=np.sin((lat2-lat1)*p/2)**2+np.cos(lat1*p)*np.cos(lat2*p)*np.sin((lon2-lon1)*p/2)**2
    return 12742*np.arcsin(np.sqrt(a))
soc={}
for (u,s),g in d.groupby(['union_u','society_u']):
    r=g.soc_rom.iloc[0]; c=cand(skel(r),r)
    soc[(u,s)]=c.iloc[0] if c.score.iloc[0]>=0.8 else None
out=[]
for i,row in d.iterrows():
    a=soc[(row.union_u,row.society_u)]
    sub=P if a is None else P[hav(a.lat,a.lon,P.lat,P.lon)<20]
    if len(sub)==0: sub=P
    c=cand(row.sk,row.rom,sub)
    b=c.iloc[0]; ok=b.score>=(0.85 if a is not None else 0.92)
    out.append(dict(row[['lot','union_u','society_u','phad_u','rom']],osm_name=b['name'],lat=b.lat if ok else np.nan,lon=b.lon if ok else np.nan,score=round(b.score,3),anchored=a is not None))
o=pd.DataFrame(out); o.to_csv('out/phads_geocoded.csv',index=False)
print('societies anchored',sum(v is not None for v in soc.values()),'of',len(soc))
print('phads matched',o.lat.notna().sum(),'of',len(o)); print(o.groupby('union_u').lat.apply(lambda s:s.notna().mean()).round(2))
print(o[o.union_u=='औबेदुल्लागंज'].sample(40,random_state=2)[['phad_u','rom','osm_name','score']].to_string())
