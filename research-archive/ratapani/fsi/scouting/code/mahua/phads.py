"""Parse MP MFP Federation 'Phad list 2026' (Krutidev PDF text) for unions around Ratapani, convert to Unicode."""
import re, pandas as pd, sys
sys.path.insert(0,'.')
from krutidev import conv
T=open('../papers_r12_mahua/mfp/Phad2026.txt',encoding='utf-8',errors='ignore').read().splitlines()
rows=[]; cur=None
for ln in T:
    if not ln.strip() or 'QM+ksa ds uke' in ln or 'dzekad' in ln: continue
    m=re.match(r'^\s{0,4}(\d{1,3})\s{2,}(.*)$',ln)
    if m:
        toks=[t.strip() for t in re.split(r'\s{2,}',m.group(2)) if t.strip()]
        if len(toks)<2: cur=None; continue
        cur=dict(lot=int(m.group(1)),union=toks[0],society=toks[1]); 
        for p in toks[2:]: rows.append(dict(cur,phad=p))
    elif cur is not None and re.match(r'^\s{10,}',ln):
        for p in [t.strip() for t in re.split(r'\s{2,}',ln) if t.strip()]:
            if re.fullmatch(r'\d+',p): continue
            rows.append(dict(cur,phad=p))
d=pd.DataFrame(rows)
for c in ['union','society','phad']: d[c+'_u']=d[c].map(conv)
print(d.union_u.value_counts().head(70).to_string())
keep=['औबेदुल्लागंज','रायसेन','सीहोर','भोपाल']
s=d[d.union_u.isin(keep)]
print(s.groupby('union_u').agg(lots=('lot','nunique'),phads=('phad','size')))
s.to_csv('out/phads_ratapani_unions.csv',index=False)
print(s[s.union_u=='औबेदुल्लागंज'][['lot','society_u','phad_u']].to_string())
