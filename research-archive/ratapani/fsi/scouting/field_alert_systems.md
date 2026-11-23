# Field alert systems: what others do, and what we should copy

Searched October 2026 (web plus the Consensus paper search). This builds on `../fast3_alert_system.md`, `../what_fsi_does.md` and `field-system/README.md`, and doesn't repeat them.
Every item below has a link. Lines marked **(inferred)** are my reading, not something the source says.

---

## A. Indian state systems (closest to us)

### 1. Odisha OFMS (Odisha Forest Management System) and the OFMS 2.0 app
- Links: https://odishaforest.in/forest-management/about-forest-management ; season report PDF: https://odishaforest.in/admin/data/ckeditor/images/300620262723599780_Firepointsummary_report_1782820992.pdf ; app: https://apkcombo.com/ofms-2-0/gov.orsac.ofms2/
- FSI alerts come in through a direct API. A server-side geoprocess sends each alert to the phone of the beat guard who covers it (about 8,000 phones). The app navigates offline to the point. Staff upload geotagged photos and the action taken.
- **The point is marked "attended" automatically once the phone is within 200 m of the FSI point.** Source: NRSC slide deck, https://www.nrsc.gov.in/sites/default/files/pdf/ebooks/drm/S-V_ForestFireDrought.pdf (the link returned 404 when I tried it; the quote comes from the search snippet).
- Share of points responded to: 92% (2022), 99% (2023), 99.86% (2024), 99.94% (2025), 99.97% (2026 to June). The 2026 report has 20,841 FSI points: 20,037 inside forest blocks and 804 outside, plus 2,885 large-fire points. It also gives burnt hectares by division.
- The published report gives **% responded only. It has no split into fire found, no fire, or outside forest.** **(inferred)** A response rate near 100% that arrives with no outcome split suggests "responded" just means "reached 200 m". That says nothing about what staff found.
- **Use for us:** auto-mark arrival with a geofence (we use 1 km for photos; also log the first time the phone came within 200 m). Copy their one-page report layout: by division, inside versus outside forest, large fires on their own line, % responded. But always add the outcome split, which Odisha leaves out.

### 2. Uttarakhand "Forest Fire Uttarakhand" app (2025, statewide)
- Links: https://www.etvbharat.com/en/!state/uttarakhand-introduces-first-of-its-kind-mobile-application-to-tackle-forest-fires-enn25062201843 ; https://www.etvbharat.com/en/!bharat/uttarakhand-ifos-officer-develops-apps-to-mitigate-forest-fires-enn25021804429
- Piloted in Rudraprayag division (2020–22) and now used by about 7,000 workers. **Field staff can update a fire only from within 500 m of it.** The public can geotag fires through a QR-code download. The state says response time fell by "5–6 hours", but the article doesn't say how this was measured.
- **Use for us:** a hard rule that the "fire out" or "no fire" status can only be set near the point, not only flagged afterwards. A public report button could come later.

### 3. Uttarakhand's ground check of FSI alerts (Jan 2026): the best false-alarm figure for India
- Link: https://www.etvbharat.com/en/state/uttarakhand-forest-department-claims-that-most-of-fsi-forest-fire-alert-false-enn26013007036
- 1 Nov 2025 to 20 Jan 2026 (the off-season): 1,952 alerts. Field checks found 132 real forest fires (6–7%), 766 "completely false", 754 outside forest, and about 300 controlled burns by the department (sums to exactly 1,952; the 132 fires burnt 18.84 ha). The state has written to FSI (PCCF letter to DG FSI, 31 Dec 2025; an earlier cut of 1,050 checked alerts gave 64 real / 377 false / 479 outside / 130 controlled). See `field_alert_systems_fullread.md`.
- **(inferred)** This is winter with few fires. Peak-season rates will be higher. Still, outside-forest fires plus controlled burns made up more than half of all alerts.
- **Use for us:** our outcome codes already cover these classes (no fire / outside forest / controlled burn). Keep all four, and report them as % of alerts each week. Add a controlled-burn register (planned burns entered ahead of time) so those alerts close themselves.

### 4. Tamil Nadu Real-time Forest Fire Monitoring System, plus the State Fire Control Centre (Apr 2024)
- Links: https://forests.tn.gov.in/pages/view/Real-time_Forest_Fire_Monitoring_System (returned 503 when fetched; details come from the search snippet) ; https://forests.tn.gov.in/pages/view/Forest_Fire_Control_Centre ; https://kygcms.tn.gov.in/cms_migrated/document/press_release/pr080223_e_260.pdf
- A frontline app with an admin dashboard. A beat guard **accepts or rejects** each alert ("outside forest" is a reject reason). The dashboard shows status, GPS, burnt area, land type and **time the fire was put out**. The press release cites FSI: 91% of large fires controlled within 24 h.
- **Use for us:** add "time fire was put out" (separate from arrival time), and an early accept/reject step so a guard can close farm fires from the map without a visit, which a ranger then checks.

### 5. Maharashtra MFD Geo-portal (2019)
- Link: https://geospatialworld.net/gsi/2019/ppt-2019/Real-Time-Forest-Governance-praveen.pdf
- FSI alerts shown as a WMS layer every 2–4 h, **coloured by age (today / yesterday / day before)**. Feeds a Nagpur command room together with the "Hello Forest 1926" call line.
- **Use for us:** colour alerts on our control-room map by age as well as by state.

### 6. FSI FAST 3.0 and Van Agni
- Links: https://fsiforestfire.gov.in/document/faq.pdf ; paper: Elavarasan et al. 2019, https://revistaeletronica.icmbio.gov.br/index.php/BioBR/article/view/1140
- More than 50,000 users. The stated purpose of feedback is to "track combat operations" and collect cause and fire type. **There is no public figure on how many alerts get feedback.** NRSC told a NASA webinar it does **no** ground validation of VIIRS/MODIS. Validation comes only from state feedback: https://directreadout.sci.gsfc.nasa.gov/ndrc_documents/NDRC9_Webinar_Minutes_2019.05.15.pdf
- **Use for us:** our CSV export should match FSI's feedback fields exactly, so it can be pasted or uploaded back to FSI. This closes the loop that NRSC says is the only validation that exists.

### 7. Andhra Pradesh (Markapur)
- Link: https://satnews.com/2021/03/22/satellite-based-technology-jhelping-andhra-pradesh-stop-forest-fires/
- FSI SMS goes to the range officer. More than 100 contract fire watchers in groups. No figures for verification or response time.
- **Use for us:** nothing new, except that fire watchers (not only beat guards) need logins.

---

## B. International operational systems

### 8. Indonesia SiPongi + Manggala Agni "groundcheck"
- Links: https://sipongi.menlhk.go.id ; https://ksdae.kehutanan.go.id/storages/81eeb9dca3654a1bb7d26b49032f4876.pdf ; 2026 example: https://www.metrotvnews.com/read/kewCjA8P-218-titik-panas-terpantau-di-singkawang-sejak-februari-2026
- Policy says a hotspot only counts as a fire **after a Manggala Agni ground check**. Teams go out daily from the SiPongi hotspot list and report to their Daops base.
- **Use for us:** the same rule in our language. An alert stays "unconfirmed" until a field report is accepted, and only accepted reports go into the ground-truth export.

### 9. Global Forest Watch: Forest Watcher app (WRI)
- Links: https://www.wri.org/insights/forest-watcher-brings-data-straight-environmental-defenders ; manual: https://content.globalforestwatch.org/wp-content/uploads/2020/09/Forest-Watcher-Field-Manual-English.pdf ; alert subscriptions: https://globalforestwatch.org/subscribe
- Download an area of interest plus its alerts (GLAD and VIIRS fire) **before** going out. Navigate offline, record **route tracks**, GPS points, photos and custom forms, then upload when back in signal. Open source.
- **Use for us:** pre-download the beat's alerts and map tiles while in signal, and record a **route track** on the way to the point (proof of travel, not only arrival).

### 10. SMART (Spatial Monitoring and Reporting Tool) + SMART Mobile / Connect
- Links: https://globalconservation.org/methodology/global-park-defense/smart-spatial-monitoring-and-reporting-tool/ ; https://www.tfcaportal.org/system/files/resources/Excursion%20session%20III%20-%20SMART%20training%20-%20PPF.pdf ; https://news.mongabay.com/2017/10/smart-and-well-connected-reserve-patrol-data-system-adds-communications-capacity/
- The standard patrol tool in about 100 countries. SMART Mobile **automatically logs GPS and time for every observation and the full patrol track**. Each site customises its data model. Connect pushes key observations in real time. Fire alerts come in only as a planning layer.
- **(inferred)** Indian tiger reserves use M-STrIPES (a SMART-like system). Ratapani staff may already carry it. A secondary source (Indian Masterminds feature) says M-STrIPES records forest fires, but I found no fire field definitions.
- **Use for us:** keep our fields close to a SMART-style "fire incident" observation so data could be exported to SMART or M-STrIPES later. Ask MP whether Ratapani patrols already use M-STrIPES.

### 11. EarthRanger: FIRMS integration
- Links: https://earthranger-support.helpjuice.com/en_US/firms-configuration ; https://earthranger-support.helpjuice.com/en_US/firms-fire-reports-
- A plugin turns each FIRMS detection inside a chosen area into an EarthRanger "Event" (a FIRMS Report type) on the ops map, next to ranger tracks. The docs don't describe a response workflow.
- **Use for us:** confirms our design (alert becomes a task on the same map as staff). Nothing more to copy.

### 12. NASA FIRMS alert service
- Link: https://firms.modaps.eosdis.nasa.gov/alerts/
- Free email alerts for a drawn polygon or protected area (MODIS plus three VIIRS satellites), sent in near real time or as a daily or weekly digest.
- **Use for us:** a zero-code backup channel. Register the Ratapani polygon for the range officer's email in case our server is down.

### 13. Sweden: automated VIIRS alerts with verified false alarms (paper, 2026)
- Dybbroe et al. 2026, J. Pyrogeography: https://consensus.app/papers/details/7c62f28c4fa754e28e49653e4c9ec9a2/?utm_source=claude_desktop
- 17 min from overpass to alert. **Verified false alarms about 10%**, mostly solar-panel arrays, greenhouses and metal roofs. **29% of satellite detections raised the alarm before any other source.**
- **Use for us:** the solar/industry mask (on our "not done" list) is the biggest single fix. Also record "who knew first" in each report (satellite / watchtower / villager / patrol) so we can measure the 29% figure for Ratapani.

### 14. Australia DEA Hotspots and Canada CWFIS (how agencies frame satellite points)
- Links: https://knowledge.dea.ga.gov.au/data/product/dea-hotspots/ ; https://cwfis.cfs.nrcan.gc.ca/home
- Both say hotspots are **not** for safety-of-life decisions. DEA puts location accuracy at ±2 km at best. Agencies confirm through ground or air reports. CWFIS shows agency-confirmed fires as a **separate layer** from satellite hotspots.
- **Use for us:** keep "satellite point" and "confirmed fire" as separate layers on the map and in the export.

### 15. Brazil INPE Queimadas / PrevFogo
- Links: https://agenciabrasil.ebc.com.br/geral/noticia/2024-09/brasil-ja-registou-mais-de-154-mil-focos-de-calor-este-ano ; https://outraspalavras.net/outrasmidias/contra-queimadas-as-brigadas-indigenas/
- INPE hotspots are sent to brigade bases. I found **no** public field-verification app or SOP.
- **Use for us:** nothing to copy beyond what is above.

---

## C. Ground-truth rates of VIIRS/MODIS (for setting expectations)

| Study | Where | Finding | Link |
|---|---|---|---|
| Uttarakhand Forest Dept (field) | India, winter 2025–26 | 6–7% of FSI alerts were real forest fires | item 3 |
| Juvanhol et al. 2023 | Brazil savanna PA | Only 30% of MODIS active fires fell in a burned area | https://consensus.app/papers/details/b9055731d0c35487bc996ad8c4cbdd5a/?utm_source=claude_desktop |
| Pinto et al. 2024 | Serra da Canastra, Brazil | 99.4% (VIIRS) / 95% (MODIS) matched Sentinel-2 scars. Scars under 1 km² often missed | https://consensus.app/papers/details/13a15ac495735e858fa5521579acc8a9/?utm_source=claude_desktop |
| Coskuner 2022 | Turkey vs ground fire DB | VIIRS caught only 1.3–25.6% of ground-recorded fires (misses, not false alarms) | https://consensus.app/papers/details/855fc61a41435fb199bf3e9633c0c571/?utm_source=claude_desktop |
| Sofan et al. 2022 | Indonesia | A static mask (volcano, industry, water) removed 13% of VIIRS points as false (7,139 of 54,411 in 2021; 97% user accuracy), "to support efficient ground validation" | https://consensus.app/papers/details/1a36e80341265c83bcac2053e293ea04/?utm_source=claude_desktop |
| Schroeder et al. 2008 | Amazon | MODIS commission about 35% in clearing areas, but more than 80% of "false" points had a recent burn scar nearby | https://consensus.app/papers/details/d06e9a243014556395bcdff0d00385cc/?utm_source=claude_desktop |
| Filizzola et al. 2016 | Italy, 950 ground/air checks | Commission 18% (3–30%). Satellite was the only alert in 348 cases | https://consensus.app/papers/details/f235fd376e975e23bf40e12ef54d3732/?utm_source=claude_desktop |

**(inferred)** Taken together: false-alarm rates swing from about 1% to more than 90% depending on season, land mask and whether farm fires count. That's why our own accepted reports are the only figure we can trust for Ratapani. Schroeder's point matters for us: a "no fire" report can be an old burn, so "burnt, fire out" must stay its own outcome (it already is).

---

## D. Does alert feedback or field response change outcomes?

- **Slough et al. 2021, PNAS (RCT, 76 Peruvian communities):** GFW alerts plus training **plus paid patrols** cut forest loss by about 8 ha per community in year 1. The result is imprecise, and the effect was largest where threat was highest. Monitors with incentives replaced free-riding volunteer patrols. https://consensus.app/papers/details/1c290ed204cd575496726ec009e8f83b/?utm_source=claude_desktop
- **Moffette et al. 2021, Nature Climate Change:** having alerts available did nothing. *Subscriptions* (someone actually receiving them) cut deforestation 18% in Africa, mostly in protected areas and concessions. https://consensus.app/papers/details/42fa6cf109205a2bae9cc848e27ebf3c/?utm_source=claude_desktop
- **Cappello et al. 2022, Remote Sensing (Peru PNCB):** 1,853 community reports against 445 alerts. Reporting by phone gave **faster data and a higher response rate** than paper. Delays in passing alerts on were the main weakness. https://consensus.app/papers/details/9a104feb42a652be9c035cd6dbe2b9fa/?utm_source=claude_desktop
- **Assunção et al. 2023, AEJ Applied (Brazil DETER):** alerts only work when enforcement acts on them. Clouds that blocked alerts meant fewer enforcement visits and more clearing. https://consensus.app/papers/details/2f5c39bb9c5452b48872864e29e0ceec/?utm_source=claude_desktop
- **Finer et al. 2018, Science:** a five-step protocol from satellite alert to intervention. Detection is not enough without an institution that acts. https://consensus.app/papers/details/c3268ca2454c5d20ac5e38a991365feb/?utm_source=claude_desktop
- **Use for us:** the evidence says the gains come from *named people receiving alerts and being held to a response*, not from the alerts themselves. Push alerts to a named guard (SMS/WhatsApp, on our "not done" list), and show each beat's % visited and median hours to the range officer every week. Melghat's payment result (in `what_fsi_does.md`) points the same way.

---

## E. Photo and location anti-fraud, and offline field apps

### 16. ODK Collect audit log
- Link: https://docs.getodk.org/form-audit-log/ ; forum: https://forum.getodk.org/t/how-can-i-configure-an-audit-log-to-track-changes-and-location/21872
- Logs every form event with a timestamp and (optionally) a background GPS track. **When a mock location app is in use, accuracy is recorded as 0.** Turning tracking off is itself logged. Edits can require a reason.
- **Use for us:** send a mock-location flag from the phone (a browser can't see it; an Android wrapper or ODK can). Log time spent on the form, and require a reason when a report is edited after it was submitted.

### 17. KoboToolbox metadata (`start`, `end`, `deviceid`, `audit`)
- Links: https://support.kobotoolbox.org/metadata_xls.html ; https://cran.r-project.org/web/packages/robotoolbox/vignettes/audit-data.html
- Records form start and end, an ID for the phone, and per-question timing plus GPS. All offline.
- **Use for us:** record a device ID with each report and flag one device filing for two guards, or one guard on two devices. **(inferred)** If the browser-only approach struggles offline, a KoboCollect/ODK form pointed at our API is a fallback.

### 18. PMAY-G Awaas App (India housing scheme)
- Links: https://informaticsweb.nic.in/appscape/awaas ; https://eparlib.sansad.in/bitstream/123456789/2994293/1/AU2547_oaIMWH.pdf
- India's largest geotagged-photo checking system. Photos are geotagged and time-stamped "to reduce the risk of fraud". The 2024 version adds **Aadhaar face authentication** and works offline. Officers re-inspect a sample (about 10% at block level and 2% at district, at each construction stage, per Parliament answers).
- **Use for us:** a ranger re-checks a random sample in person (for example 5–10% of accepted reports per range). A face match is too heavy for us. **(inferred)** One selfie at the fire point, kept in the record, is a cheap stand-in.

### 19. ProofMode (Guardian Project / WITNESS), with C2PA content credentials
- Links: https://guardianproject.info/apps/org.witness.proofmode/ ; https://guardianproject.info/code/c2pa
- At capture it signs each photo, with a SHA-256 hash, phone sensor and location data, and optional third-party timestamps, and keeps the originals untouched. Not audited and not yet tested in court.
- **Use for us:** we already hash for `photo_reused`. **(inferred)** If tampering becomes a real problem, take photos in a signing app like ProofMode instead of the gallery. That's overkill for the first season.

### 20. Mock-location detection (Android)
- Link: https://stories.hypertrack.com/hypertrack-detects-mock-locations-android/
- Android flags each fix with `isFromMockProvider()`. Server-side signs of a fake fix: fixed values for speed, bearing or accuracy, and evenly spaced timestamps.
- **Use for us:** on the server, flag a fix that has suspiciously round accuracy, zero speed for the whole trip, or identical coordinates across reports.

---

## Ranked top 5 to adopt

1. **Record what was found, not only "responded".** Odisha reports 99.97% "responded" with no split into fire / no fire / outside forest / controlled burn. Uttarakhand's split showed only 6–7% were real forest fires. Our outcome codes and weekly % by outcome are the gap in Indian practice. Keep them central, add "time fire put out" (Tamil Nadu), and send the export back to FSI in its own feedback fields.
2. **Proximity rules at two levels.** Auto-log the first time the phone came within 200 m (Odisha), and only allow a closing status from near the point (Uttarakhand, 500 m). Add a route track on the way there (Forest Watcher, SMART). These are cheap and harder to fake than a photo alone.
3. **Push alerts to a named person, and publish each beat's response numbers.** The studies agree that impact comes from someone receiving the alert and being accountable for it (Moffette, Slough, Assunção). SMS/WhatsApp push plus a weekly per-beat table of % visited and median hours to visit.
4. **Cut false alerts before they become field tasks.** Add a solar, industry and kiln mask (Sweden: most of its 10% false alarms; Indonesia mask removed 13%), a planned-burn register so controlled burns close themselves, and a guard accept/reject step for obvious farm fires (Tamil Nadu), checked by a ranger.
5. **Light anti-fraud plus random re-checks.** Device ID, mock-location flag, edit reasons (ODK/Kobo), plus a 5–10% random in-person re-check by the ranger (PMAY-G). Save signed capture (ProofMode/C2PA) for later.

Also worth doing: add a "who knew first" field (satellite / watchtower / villager / patrol). That would measure, for Ratapani, Sweden's "29% first alarm" figure and Melghat's watchtower lag.
