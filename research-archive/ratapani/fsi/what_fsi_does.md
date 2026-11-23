# What the FSI decks say, in simple words

All five files in E:\FIRE\fsi_data were read in full (text and speaker notes): 4 slide decks and 1 PDF from FSI's officer training, Dehradun, 14–18 Sep 2026.

## 1. How India finds fires today (FSI alert system)

- FSI takes fire points from two NASA satellites: MODIS (1 km squares) and VIIRS (375 m squares, now the main one). The data comes in through ISRO's ground station at Shadnagar.
- Alerts go out at least 6 times a day by SMS, email (KML and CSV files) and the Van Agni portal. They reach staff down to range and beat level. Uttarakhand alone has 17,729 people signed up.
- **Large fire tracking:** when 3 or more touching VIIRS pixels light up (about 40 ha or more), FSI tracks that fire's outline until it is out.
- **Feedback:** field staff mark each alert as a real fire or not. This is the ground truth we lack, but it sits behind a login. Madhya Pradesh has sent 14 feedbacks so far this season.
- **Pre-fire alert:** FSI sends a danger rating once a week, based on weather forecasts. India's rating is based on weather only, with little difference between fuel types (deck 5 calls it "developing").
- FSI's public archive (2004 to June 2025) has only date, sensor, latitude, longitude and time: the same as NASA FIRMS, which we already have.

## 2. What FSI and its partners do to predict fire

| Method | What it is | Scale | Useful for us? |
|---|---|---|---|
| Weekly fire danger rating | Weather-based index per zone | Coarse, weekly | No. Our model already beats fire-weather indices. |
| Fire risk zone maps (2023-24 report) | Fire-prone classes from past fire counts | District / forest level | Weak. We already use each cell's own burn history. |
| **Surface fuel load map** (Dr Sunil Chandra) | Forest type (17 classes) × canopy density (4) × slope (4) = 272 groups. Each group gets a fuel load from oven-dried 1 ft × 1 ft floor samples. Classes: under 20, 20–40, 40–60, over 60 g/ft². | National, one date | Worth a test (idea B below). |
| **C-DAC fire-spread forecast** (Dr Manish Kale) | A physics model (WRF-SFIRE) on a supercomputer. Takes a fire's start point, weather, fuel and terrain, and maps where the fire will spread over 24–48 h. Used live in Sikkim in March 2024. | Per fire, after it starts | Only for spread. It needs a known start point, so it can't say where new fires will start. Our spread model found wind adds nothing at 500 m. |
| Tamil Nadu beat ranking | Every beat ranked into 5 risk classes and fed into a 2026 prediction model | Beat | Shows departments think in beats, as we do. |

FSI's own figure: 93% of fires start on the forest floor (low-intensity litter fires). More than 95% are started by people (mahua and tendu collection, grazing, crop burning).

## 3. Lessons from the case studies that touch our work

- **Melghat (dry teak forest like Ratapani, Maharashtra).** Taken over a whole season, Sentinel-2 burn maps confused leaf fall with burns. They flagged 44% of the division in two years whose ground records differed by 92%. *We checked: our labels compare each pixel with its surroundings over short gaps, and dry-cell scars match VIIRS as often as any others. They are fine.*
- **Melghat fire sizes.** The median fire in the ground register was under 3 ha, while a VIIRS pixel covers about 14 ha. So counting pixels overstates burnt area about 4 times. Our labels drop scars under 2 ha.
- **Melghat timing.** A watchtower guard reported a fire 2 hours before the NASA email arrived, and FSI sent no alert at all. Satellites miss or lag many small fires.
- **Melghat register.** The division kept a GPS-measured fire register checked by an officer (ACF), compartment by compartment. This is the ground truth that satellite products are missing.
- **Melghat rewards.** Paying villages for zero fires cut fires from 218 to 35 in one season. Fires came back when the payments stopped. Human behaviour moves fire numbers a lot from year to year.
- **Odisha (Angul).** Patrols are checked on a 2 km × 2 km grid. Alerts fell from 738 (2023) to 333 (2026).
- **Uttarakhand.** 2,393 beats, a fire app, and a strategy to reach every fire in the "first 60 minutes". Pine needle collection is used to cut fuel. Each fire's area is reported back through the app, which is another ground register.
- **Nainital and Sariska.** FSI checked burn-severity maps on the ground. Most burns were "low severity", which fits light litter fires that are hard to see from space.

## 4. What none of the files has

There are no beat or compartment boundaries, no fire records for Madhya Pradesh or Ratapani, and no maps or data files we can download.

## 5. Ideas to borrow or test for Ratapani

A. **Done:** true 2-day labels (the scar shows where, VIIRS shows which day). See `true_lead_labels.parquet`. The pipeline thread is retraining on them.
B. **FSI-style fuel groups as an input.** Group each cell by forest type × canopy density × slope, and test whether that adds anything over our per-cell dryness. (We don't have FSI's forest type map, so the first try would use WorldCover, canopy from NDVI, and SRTM slope.)
C. **Large fire flag.** Use FSI's rule (3 or more touching VIIRS pixels) as a feature or a separate target. Big fires behave differently from the many one-pixel fires.
D. **Ground truth (needs you).** Ask the MP Forest Department for the Ratapani divisions' fire register and their beat and compartment map. Also ask for the FSI alert feedback for Raisen and Sehore districts. These would fix our labels, our dates and our beats all at once.

## FSI VIIRS satellite and position accuracy (added 14 Oct 2026, from the field alerts thread)
FSI's VIIRS alerts came from S-NPP from Nov 2025 to 26 Apr 2026, and from NOAA-21 from about May 2026 (matched against FIRMS pass times). In the S-NPP months, FSI pixel positions are a median 0.25 km off NASA's FIRMS positions (only 13% within 0.1 km). In the NOAA-21 months, 98% are within 0.1 km. For any Nov-Apr FSI-to-FIRMS point join, use a radius of about 0.4 km.
