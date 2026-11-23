import requests,sys
q=sys.argv[1]; n=int(sys.argv[2]) if len(sys.argv)>2 else 15
r=requests.get('https://api.openalex.org/works',params={'search':q,'per-page':n,'mailto':'research@example.org'}).json()
for w in r.get('results',[]):
    oa=w.get('open_access',{}); 
    print(w['publication_year'],'|',w['display_name'][:150],'|',w.get('doi'),'|',oa.get('oa_url'),'| cit',w['cited_by_count'])
