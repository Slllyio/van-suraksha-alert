import json,glob,csv,datetime as dt,collections
G=json.load(open('gran.json'))
F=[]
for f in glob.glob('/mnt/project-files/fire-alert-scars/alerts/viirs-*_20*.csv'):
    for r in csv.DictReader(open(f)):
        t=dt.datetime.strptime(r['acq_date']+r['acq_time'].zfill(4),'%Y-%m-%d%H%M')
        F.append((t,float(r['latitude']),float(r['longitude'])))
F.sort()
import bisect
ts=[x[0] for x in F]
passes=collections.defaultdict(lambda:[0,0,set()])  # pass minute -> [n6h, n3h, fires]
for t0,ti,s,w,n,e in G:
    T=dt.datetime.fromisoformat(t0.replace('Z','').split('.')[0])
    k=T.strftime('%Y-%m-%dT%H:%M')
    for win,idx in ((6,0),(3,1)):
        a=bisect.bisect_left(ts,T-dt.timedelta(hours=win)); b=bisect.bisect_right(ts,T+dt.timedelta(hours=win))
        hit=[F[i] for i in range(a,b) if s<=F[i][1]<=n and w<=F[i][2]<=e and 77.34<=F[i][2]<=78.07 and 22.82<=F[i][1]<=23.11]
        if hit: passes[k][idx]=max(passes[k][idx],len(hit))
    passes[k]
def ist(k): return dt.datetime.fromisoformat(k)+dt.timedelta(hours=5,minutes=30)
def gap(k):
    h=ist(k).hour+ist(k).minute/60
    return not (0.5<=h<=2.75 or 12.5<=h<=14.75)
P=list(passes.items())
print('passes',len(P))
print('with VIIRS fire in AOI within 6h:',sum(1 for k,v in P if v[0]), ' within 3h:',sum(1 for k,v in P if v[1]))
print('  of those at hours VIIRS does NOT look (3h):',sum(1 for k,v in P if v[1] and gap(k)))
per=collections.Counter(ist(k).year for k,v in P if v[1] and gap(k)); print('per season',dict(sorted(per.items())))
hrs=collections.Counter(ist(k).hour for k,v in P if v[1] and gap(k)); print('IST hours',dict(sorted(hrs.items())))
json.dump([(k,v[0],v[1],gap(k)) for k,v in P],open('pass_fire.json','w'))
