import requests,sys,time
q=sys.argv[1]; n=int(sys.argv[2]) if len(sys.argv)>2 else 12
r=requests.get('https://api.crossref.org/works',params={'query.bibliographic':q,'rows':n,'select':'DOI,title,issued,container-title','mailto':'research@example.org'},timeout=60).json()
for w in r['message']['items']:
    y=w.get('issued',{}).get('date-parts',[[None]])[0][0]
    print(y,'|',(w.get('title') or [''])[0][:140],'|',(w.get('container-title') or [''])[0][:40],'|',w['DOI'])
