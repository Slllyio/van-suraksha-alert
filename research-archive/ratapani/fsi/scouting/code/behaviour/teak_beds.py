"""Bulk density and consumed-load numbers from Ramos-Rodriguez et al. 2019 (RBCA 14(1) e5607) Table 4/5, typed from the page images."""
PcA=[0.54,0.50,0.72,0.58,0.54,0.57,0.54,0.62,0.50,0.68]  # kg/m2 dry pre-burn
EspA=[13.33,14.33,15.33,16.33,13.67,16.67,12.00,14.00,13.33,13.33]  # cm
PcC=[0.46,0.37,0.59,0.47,0.47,0.48,0.33,0.53,0.38,0.55]
Vpf=[0.0093,0.0076,0.0119,0.0104,0.0093,0.0076,0.0093,0.0083,0.0167,0.0104]  # m/s
I=[63.21,41.41,105.46,73.79,64.25,53.96,44.84,66.51,92.45,83.70]
rb=[p/(e/100) for p,e in zip(PcA,EspA)]
print("bulk density kg/m3: min %.1f mean %.1f max %.1f"%(min(rb),sum(rb)/len(rb),max(rb)))
print("ROS m/h: min %.0f mean %.0f max %.0f"%(min(Vpf)*3600,sum(Vpf)/len(Vpf)*3600,max(Vpf)*3600))
print("consumed kg/m2 mean %.2f; consumption %.0f%%"%(sum(PcC)/10, 100*sum(PcC)/sum(PcA)))
# implied heat yield H = I/(w R)
H=[i/(w*r) for i,w,r in zip(I,PcC,Vpf)]
print("implied H kJ/kg mean %.0f"%(sum(H)/len(H)))
