"""Cover page + JPEG pages -> one compressed PDF per set, with a page index CSV.  python3 uv_atlas_pdf.py pages_dir out.pdf title"""
import sys, os, glob, matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt, pandas as pd
from PIL import Image
D, OUT, TITLE = sys.argv[1], sys.argv[2], sys.argv[3]
pages = sorted(glob.glob(f'{D}/*.jpg'))
txt = f"""{TITLE}
{len(pages)} fires, one page each. Each panel is one VIIRS look; up to 6 looks per fire (evenly spaced if more).

HOW TO READ A PANEL
  grey fill      ground that really burned before this look (fire-continuity arrival map, inside scar outline v2)
  orange fill    ground that really burned in the next 24 h  = what the forecast should cover
  blue line      the forecast: ground burned by +24 h (375 m blocks + each active front grown by its expected area)
  dotted black   the 375 m blocks seen so far
  thin red       the final scar outline v2
  red dots       detections at this look; black dots = earlier looks
  blue text      per active front: expected new ha in 24 h and chance it stops

PANEL TITLE: forecast new ha | real new ha | overlap of forecast with real (Sorensen, 1 = perfect),
             and in brackets the overlap of the simple rule "blocks + 24 ha per active front".
PAGE TITLE:  mean overlap over the fire's looks: forecast, blocks only, 24 ha rule.

Models: growth and stop models trained on ALL fires with this fire's season held out (unseen_validation/models_all_fires).
Real timing is reconstructed from all looks (84% right on photos); suppression shapes stops and edges.
Overall (unseen_validation/README.md): forecast ~0.46-0.47, blocks only 0.43, 24 ha rule 0.48 on unseen fires."""
fig = plt.figure(figsize=(13.8, 9.7)); fig.text(.05, .95, txt, va='top', family='monospace', fontsize=10.5); fig.savefig(f'{D}/_cover.png', dpi=80); plt.close(fig)
ims = [Image.open(f'{D}/_cover.png').convert('RGB')] + [Image.open(p).convert('RGB') for p in pages]
ims[0].save(OUT, save_all=True, append_images=ims[1:], resolution=80, quality=70)
pd.DataFrame(dict(page=range(2, len(pages) + 2), fire=[int(os.path.basename(p)[:5]) for p in pages])).to_csv(OUT.replace('.pdf', '_index.csv'), index=False)
print(OUT, os.path.getsize(OUT) / 1e6, 'MB')
