"""Read-only export of the beat-estimation inputs for the methods thread: Guna headline spots, ring-1 beat spots and labels, omission spots, two-labeller comparison. No coordinates."""
import glob
import re

import pandas as pd

O = "E:/FIRE/forest_loss_monitor/outputs/"
G = "E:/FIRE/forest_loss_monitor/ground_truth/"
D = O + "beat_estimation_inputs/"


def labels_for(prefix, div):
    """Labels for one division only: my file plus labeller parts named for exactly this division (Vidisha must not pick up FDCM_Vidisha)."""
    kind = "beat" if prefix == "beat_blind" else "omit"
    pat = re.compile(rf"^{kind}_{re.escape(div)}(_\d+_\d+)?\.csv$")
    files = [G + f"{prefix}_{div}_labels.csv"] + [f for f in glob.glob(O + "labeller_parts/*.csv") if pat.match(f.replace("\\", "/").split("/")[-1])]
    parts = []
    for f in files:
        try:
            parts.append(pd.read_csv(f))
        except FileNotFoundError:
            pass
    return pd.concat(parts).drop_duplicates("code") if parts else None


def main():
    lk = pd.read_csv(O + "beat_lookup.csv").set_index("zone_id")
    s = pd.read_csv(O + "final/guna_headline/sample_labelled.csv")
    fr = pd.read_csv(O + "final/guna_sample/sample_frame.csv").rename(columns={"ha": "stratum_map_ha", "n": "stratum_n"})
    s = s.merge(fr, on="stratum", how="left")
    s["Beat"] = s.zone_id.map(lk.Beat)
    s.drop(columns=["x", "y", "row", "col"]).to_csv(D + "1_guna_headline_spots.csv", index=False)
    for prefix, out in (("beat_blind", "2_ring1_beat_spots.csv"), ("omit_blind", "3_ring1_omission_spots.csv")):
        rows = []
        for k in glob.glob(G + f"{prefix}_*_key_DO_NOT_OPEN_BEFORE_LABELLING.csv"):
            div = k.replace("\\", "/").split(f"{prefix}_")[1].split("_key")[0]
            d = pd.read_csv(k).assign(Division=div)
            lab = labels_for(prefix, div)
            d = d.merge(lab, on="code", how="left") if lab is not None else d.assign(label=None)
            rows.append(d)
        b = pd.concat(rows, ignore_index=True).drop(columns=["x", "y_m", "cid"], errors="ignore").rename(columns={"group": "Range", "first": "first_farm_year"})
        b.to_csv(D + out, index=False)
        print(out, len(b), "spots,", int(b.label.notna().sum()), "labelled")
    mp = pd.concat([pd.read_csv(f).assign(Division=f.replace("\\", "/").split("/")[-1].replace("_newfarm_by_beat.csv", "")) for f in glob.glob(O + "mp_newfarm/*_newfarm_by_beat.csv")])
    ring = pd.read_csv(D + "2_ring1_beat_spots.csv").Division.unique()
    mp[mp.Division.isin(ring)][["Division", "Range", "Beat", "forest_ha", "new_farmland_ha"]].to_csv(D + "2_ring1_beat_map_areas.csv", index=False)
    a = pd.read_csv(G + "beat_blind_Shivpuri_labels.csv").rename(columns={"label": "label_first"})
    c = pd.read_csv(O + "second_labeller/labels_second.csv").rename(columns={"label": "label_second"})
    a.merge(c, on="code").to_csv(D + "4_shivpuri_two_labellers.csv", index=False)
    print("guna spots", len(s))


if __name__ == "__main__":
    main()
