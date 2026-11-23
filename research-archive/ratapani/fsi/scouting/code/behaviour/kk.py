"""Krishikosh (DSpace 7) helpers: search titles, list bitstreams of an item. usage:
 kk.py search "<query>"   |   kk.py files <item-uuid>"""
import json,sys,urllib.request,urllib.parse
B="https://krishikosh.egranth.ac.in/server/api"
def get(u):
    return json.load(urllib.request.urlopen(u,timeout=60))
if sys.argv[1]=="search":
    j=get(B+"/discover/search/objects?size=20&dsoType=ITEM&query="+urllib.parse.quote(sys.argv[2]))
    for o in j['_embedded']['searchResult']['_embedded']['objects']:
        it=o['_embedded']['indexableObject']; md=it.get('metadata',{})
        g=lambda k: (md.get(k) or [{}])[0].get('value')
        print(it['uuid'],'|',g('dc.date.issued'),'|',(g('dc.title') or '')[:120],'|',g('dc.publisher'))
else:
    j=get(B+f"/core/items/{sys.argv[2]}/bundles?embed=bitstreams")
    for b in j['_embedded']['bundles']:
        for s in b['_embedded']['bitstreams']['_embedded']['bitstreams']:
            print(b['name'],s['name'],s.get('sizeBytes'),s['_links']['content']['href'])
