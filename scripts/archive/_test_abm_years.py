import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))
from src.abm.model import VillageFireEconomy

grid_w, grid_h = 114, 139
mult = 15.0

res = []
res.append(f"Testing ABM human ignitions across different historical years (Multiplier: {mult})")
res.append("-" * 60)

for test_year in [2019, 2020, 2021, 2022, 2023]:
    print(f"Starting simulation for {test_year}...")
    model = VillageFireEconomy(width=grid_w, height=grid_h, num_villagers=500, year=test_year, human_density_multiplier=mult)
    for _ in range(30):
        model.step()
    label = "LOCKDOWN" if test_year == 2020 else "NORMAL"
    msg = f"Year {test_year} ({label}): {model.human_ignitions_today} human-induced fires expected in a 30-day window."
    print(msg)
    res.append(msg)

print("Writing to out_clean.txt...")
with open("out_clean.txt", "w") as f:
    f.write("\n".join(res))
print("Done.")
