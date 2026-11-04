"""Join my blind visual labels of the calibration chips with the key; report what separates real loss from noise.
L clear visible loss | D partial canopy loss | T transient (visible then recovered) | N no visible change | A cropland/non-forest mosaic"""
import pandas as pd

from common import OUT

LABELS = """1L 2L 3N 4N 5D 6L 7N 8D 9N 10N 11L 12N 13L 14T 15A 16A 17L 18T 19N 20D
21N 22N 23A 24A 25N 26N 27A 28L 29N 30N 31L 32A 33N 34A 35A 36L 37N 38A 39A 40A
41N 42A 43A 44A 45N 46N 47A 48A 49L 50N 51N 52T 53A 54N 55N 56A 57A 58N 59A 60L
61N 62N 63N 64A 65L 66N 67L 68N 69N 70N 71N 72A 73A 74N 75L 76N 77N 78A 79N 80A
81A 82N 83A 84A 85A 86L 87N 88N 89N 90A 91N 92A 93N 94N 95A 96A 97N 98L 99A 100A
101N 102N 103A 104A 105D 106L 107N 108D 109A 110A 111A 112T 113L 114A 115L 116L 117T 118N 119N 120L
121N 122N 123L 124A 125N 126N 127A 128A 129N 130A 131N 132A 133L 134A 135A 136N 137A 138N 139N 140N
141N 142A 143A 144L 145N 146A 147A 148A 149A 150N 151A 152A 153N 154N 155N 156A 157A 158N 159A 160N
161A 162L 163A 164N 165A 166L 167N 168A"""


def main():
    k = pd.read_csv(OUT / "calibration" / "calib_key.csv")
    lab = pd.DataFrame([(int(x[:-1]), x[-1]) for x in LABELS.split()], columns=["sample_id", "label"])
    d = k.merge(lab, on="sample_id")
    d.to_csv(OUT / "calibration" / "calib_labels.csv", index=False)
    d["real"] = d.label.isin(list("LD"))
    d["drop"] = d.pre_ndvi - d.post_ndvi
    d["rec_frac"] = (d.rec_ndvi - d.post_ndvi) / d["drop"].where(d["drop"] > 0)
    order = ["800-1200", "1200-1600", "1600-2000", "2000-2500", "2500-3000", "3000-4000", "4000-20000"]
    print(pd.crosstab(d.bin, d.label).reindex(order).to_string())
    print(pd.crosstab(d.area, d.label).to_string())
    print(d.groupby("label")[["mag", "pre_ndvi", "post_ndvi", "drop", "rec_ndvi", "last_ndvi", "base_ndvi", "dur", "burned"]].median().round(0).to_string())
    print("loss by year (all/real):", d.groupby("map_year").real.agg(["size", "sum"]).T.to_string())
    best = []
    for mag in (1200, 1600, 2000, 2500, 3000):
        for drop in (0, 500, 1000, 1500):
            for pre in (3000, 4000, 5000):
                s = d[(d.mag >= mag) & (d["drop"] >= drop) & (d.pre_ndvi >= pre)]
                if len(s) >= 8:
                    best.append(dict(mag=mag, drop=drop, pre=pre, n=len(s), real=int(s.real.sum()), precision=round(s.real.mean(), 2),
                                     recall_of_real=round(s.real.sum() / d.real.sum(), 2)))
    print(pd.DataFrame(best).sort_values(["precision", "recall_of_real"], ascending=False).head(18).to_string(index=False))


if __name__ == "__main__":
    main()
