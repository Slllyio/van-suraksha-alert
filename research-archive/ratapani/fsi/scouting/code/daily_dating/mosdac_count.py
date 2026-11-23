import requests, sys
for ds in ['3DIMG_L2P_FIR','3RIMG_L2P_FIR','3SIMG_L2P_FIR','3DIMG_L2P_SMK','3RIMG_L2P_SMK']:
    row=[]
    for y in range(2014,2027):
        r=requests.get("https://mosdac.gov.in/apios/datasets.json",params=dict(datasetId=ds,startTime=f"{y}-01-01",endTime=f"{y}-06-30",count="1"),timeout=120)
        j=r.json(); row.append(f"{y}:{j.get('totalResults','-')}")
    print(ds,' '.join(row),flush=True)
