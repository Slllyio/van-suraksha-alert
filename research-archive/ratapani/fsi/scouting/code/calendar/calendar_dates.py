"""Calendar dates 2014-2026 (sources in mp_calendar_effects.md).
Hindu festivals: python-holidays (vacanza) calendars/hindu.py tables (Holi = colour day; Holika Dahan = day before).
Akshaya Tritiya: Drik Panchang New Delhi (via search snippets) / Business Today 2026.
Eid al-Fitr India = Saudi (Umm al-Qura) table + 1 day (Indian moon sighting), Eid al-Adha India per holidays India overrides.
Lok Sabha phases: Wikipedia / ECI news. IPL finals: Wikipedia season pages. MPBSE class-12 last paper: examresults.net / news."""
H=dict(holi="2014-03-17 2015-03-06 2016-03-24 2017-03-13 2018-03-02 2019-03-21 2020-03-10 2021-03-29 2022-03-18 2023-03-08 2024-03-25 2025-03-14 2026-03-04",
 shivratri="2014-02-27 2015-02-17 2016-03-07 2017-02-24 2018-02-13 2019-03-04 2020-02-21 2021-03-11 2022-03-01 2023-02-18 2024-03-08 2025-02-26 2026-02-15",
 ram_navami="2014-04-08 2015-03-28 2016-04-15 2017-04-04 2018-03-25 2019-04-13 2020-04-02 2021-04-21 2022-04-10 2023-03-30 2024-04-17 2025-04-06 2026-03-26",
 gudi_padwa="2014-03-31 2015-03-21 2016-04-08 2017-03-28 2018-03-18 2019-04-06 2020-03-25 2021-04-13 2022-04-02 2023-03-22 2024-04-09 2025-03-30 2026-03-19",
 akshaya_tritiya="2014-05-02 2015-04-21 2016-05-09 2017-04-28 2018-04-18 2019-05-07 2020-04-26 2021-05-14 2022-05-03 2023-04-22 2024-05-10 2025-04-30 2026-04-19",
 eid="2019-06-05 2020-05-25 2021-05-14 2022-05-03 2023-04-22 2024-04-11 2025-03-31 2026-03-21 2025-06-07 2026-05-27",
 ipl_final="2014-06-01 2015-05-24 2016-05-29 2017-05-21 2018-05-27 2019-05-12 2022-05-29 2023-05-29 2024-05-26 2025-06-03 2026-05-31",
 exam_end="2017-03-31 2018-04-03 2019-04-02 2022-03-12 2023-04-01 2024-03-05 2025-03-25 2026-03-07")
H={k:v.split() for k,v in H.items()}
# Lok Sabha polling: seat -> date per year
LS={2014:{'2014-04-10':'Satna Rewa Sidhi Shahdol Jabalpur Balaghat Mandla Chhindwara Hoshangabad',
          '2014-04-17':'Morena Bhind Gwalior Guna Sagar Tikamgarh Damoh Khajuraho Bhopal Rajgarh',
          '2014-04-24':'Vidisha Dewas Ujjain Mandsaur Ratlam Dhar Indore Khargone Khandwa Betul'},
    2019:{'2019-04-29':'Sidhi Shahdol Jabalpur Mandla Balaghat Chhindwara',
          '2019-05-06':'Tikamgarh Damoh Khajuraho Satna Rewa Hoshangabad Betul',
          '2019-05-12':'Morena Bhind Gwalior Guna Sagar Vidisha Bhopal Rajgarh',
          '2019-05-19':'Dewas Ujjain Mandsaur Ratlam Dhar Indore Khargone Khandwa'},
    2024:{'2024-04-19':'Sidhi Shahdol Jabalpur Mandla Balaghat Chhindwara',
          '2024-04-26':'Tikamgarh Damoh Khajuraho Satna Rewa Hoshangabad',
          '2024-05-07':'Morena Bhind Gwalior Guna Sagar Vidisha Bhopal Rajgarh Betul',
          '2024-05-13':'Dewas Ujjain Mandsaur Ratlam Dhar Indore Khargone Khandwa'}}
# district -> main Lok Sabha seat (approximate; districts split across seats get the seat holding most of their area)
DIST_SEAT=dict(Sidhi='Sidhi',Singrauli='Sidhi',Shahdol='Shahdol',Anuppur='Shahdol',Umaria='Shahdol',Jabalpur='Jabalpur',
 Mandla='Mandla',Dindori='Mandla',Seoni='Balaghat',Balaghat='Balaghat',Chhindwara='Chhindwara',Narmadapuram='Hoshangabad',
 Narsinghpur='Hoshangabad',Betul='Betul',Harda='Betul',Rewa='Rewa',Satna='Satna',Tikamgarh='Tikamgarh',Chhatarpur='Khajuraho',
 Panna='Khajuraho',Katni='Khajuraho',Damoh='Damoh',Sagar='Sagar',Vidisha='Vidisha',Raisen='Vidisha',Bhopal='Bhopal',Sehore='Bhopal',
 Rajgarh='Rajgarh',Guna='Guna',Shivpuri='Guna',Ashoknagar='Guna',Gwalior='Gwalior',Bhind='Bhind',Datia='Bhind',Morena='Morena',
 Sheopur='Morena',Dewas='Dewas',Shajapur='Dewas',Ujjain='Ujjain',Mandsaur='Mandsaur',Neemuch='Mandsaur',Ratlam='Ratlam',
 Jhabua='Ratlam',Alirajpur='Ratlam',Dhar='Dhar',Indore='Indore',Khargone='Khargone',Barwani='Khargone',Khandwa='Khandwa',Burhanpur='Khandwa')
DIV_DIST={'Sehore_Project':'Sehore','Obedullahganj':'Raisen','Kundam_Proj_Jabalpur':'Jabalpur','Dewas':'Dewas','South_Chhindwara':'Chhindwara',
 'South_Balaghat':'Balaghat','Indore':'Indore','Raisen':'Raisen','Mohgaon_Proj_West_Mandla':'Mandla','Kundam_Proj_Katni':'Katni',
 'Lamta_Proj_S_Balaghat':'Balaghat','South_Seoni':'Seoni','Khandwa':'Khandwa','Narsinghpur':'Narsinghpur','Barwah':'Khargone',
 'Singrauli':'Singrauli','Sehore':'Sehore','Barghat Project':'Seoni','Umaria_Project':'Umaria','North_Betul':'Betul','Umaria':'Umaria',
 'North_Balaghat':'Balaghat','FDC_Khandwa':'Khandwa','South_Betul':'Betul','Jabalpur':'Jabalpur','Lamta_Proj_N_Balaghat':'Balaghat',
 'Dindori':'Dindori','Noradehi':'Sagar','Rampur_Bhatodi_Proj':'Betul','Hoshangabad':'Narmadapuram','East_Chhindwara':'Chhindwara',
 'Bhopal':'Bhopal','Burhanpur':'Burhanpur','Satna':'Satna','Vidisha':'Vidisha','Katni':'Katni','North_Seoni':'Seoni','North_Panna':'Panna',
 'West_Chhindwara':'Chhindwara','Chhatarpur':'Chhatarpur','West_Mandla':'Mandla','West_Betul':'Betul','Rewa':'Rewa','Damoh':'Damoh',
 'Harda':'Harda','Mohgaon_Proj_Dindori':'Dindori','Anuppur':'Anuppur','East_Mandla':'Mandla','North_Shahdol':'Shahdol','South_Sagar':'Sagar',
 'BTR':'Umaria','Mohgaon_Proj_East_Mandla':'Mandla','South_Panna':'Panna','Alirajpur':'Alirajpur','Sidhi_FDCM':'Sidhi','SANJAY_DUBRI':'Sidhi',
 'South_Shahdol':'Shahdol','Panna_TR':'Panna','North_Sagar':'Sagar','Guna':'Guna','Madhav_National_Park':'Shivpuri','Dhar':'Dhar',
 'Kuno_Palpur':'Sheopur','Satpura_TR':'Narmadapuram','Ashok_Nagar':'Ashoknagar','Kanha Tiger Reserve':'Mandla','Chhindwara_Project':'Chhindwara',
 'Sidhi':'Sidhi','Khargone':'Khargone','Ujjain':'Ujjain','Neemuch':'Neemuch','PTR MP':'Seoni','Ratlam':'Ratlam','Gwalior':'Gwalior',
 'Shivpuri':'Shivpuri','Sendhwa':'Barwani','Bhind':'Bhind','Jhabua':'Jhabua','Sheopur':'Sheopur','Datiya':'Datia','Mandsaur':'Mandsaur',
 'Shajapur':'Shajapur','Barwani':'Barwani','Rajgarh':'Rajgarh','Tikamgarh':'Tikamgarh','Morena':'Morena','FDCM_Vidisha':'Vidisha'}
# Census 2011 ST share (%), Wikipedia "Tribals in Madhya Pradesh" district table (from Census 2011 PCA)
ST=dict(Bhopal=2.89,Raisen=15.39,Rajgarh=3.48,Sehore=11.10,Vidisha=4.63,Morena=0.87,Bhind=0.36,Sheopur=23.47,Gwalior=3.55,Ashoknagar=9.71,
 Datia=1.91,Guna=15.37,Shivpuri=13.20,Indore=6.64,Alirajpur=88.98,Barwani=69.42,Burhanpur=30.36,Dhar=55.94,Jhabua=87.01,Khandwa=35.04,
 Khargone=38.98,Jabalpur=15.23,Balaghat=22.51,Chhindwara=36.81,Dindori=64.69,Katni=24.59,Mandla=57.87,Narsinghpur=13.36,Seoni=37.96,
 Narmadapuram=15.89,Betul=42.34,Harda=27.99,Rewa=13.19,Satna=10.37,Sidhi=27.80,Singrauli=32.59,Sagar=9.33,Chhatarpur=4.18,Damoh=13.15,
 Panna=16.81,Tikamgarh=4.69,Shahdol=44.65,Anuppur=47.85,Umaria=46.63,Ujjain=2.45,Dewas=17.44,Mandsaur=2.47,Neemuch=8.65,Ratlam=28.17,Shajapur=2.50)
