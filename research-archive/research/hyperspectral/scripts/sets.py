GIS=['elev','slope','rugged','tpi5','south','lc_forest','lc_scrub','lc_grass','lc_sal','lc_teak','lc_drymix','lc_moistmix','lc_bamboo','lc_degraded','forest_5k','farm_5k','d_edge_in','d_road','d_village','villages_5k','road_km_5k']
HIST=['yrs_burnt','mean_burnt','last_gap','burnt_last']
S2c=[c for c in d if c.startswith('s2_')]; VN=[c for c in d if c.startswith('pv')]+[c for c in d if c.startswith('v_')]; HY=[c for c in d if c.startswith('pf')]+[c for c in d if c.startswith('h_')]
sets={'history+GIS':HIST+GIS,'+S2-like':HIST+GIS+S2c,'+S2+Pixxel-like VNIR':HIST+GIS+S2c+VN,'+S2+full EMIT':HIST+GIS+S2c+VN+HY,
      'S2-like only':S2c,'Pixxel-like only':VN,'full EMIT only':S2c+VN+HY,'SWIR litter/water indices only':[c for c in d if c.startswith('h_')]}
