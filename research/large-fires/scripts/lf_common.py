"""Large-fire study (19 Oct 2026): shared paths. Grid = all-MP 500 m grid (EPSG:32643, X0 399000, Y1 2996000, 1829 x 1332).
Big intermediates go to scratch SC only; results to research/large-fires/results."""
import os
P = '/mnt/project-files/'
SC = os.environ.get('LF_SC', '/tmp/claude-0/-home-user/a4fa3bb5-4e28-5c69-87d5-fe1aec863117/scratchpad/lf/')
HERE = P + 'research/large-fires/'
OUT = HERE + 'results/'
X0, Y1, S, W, H = 399000.0, 2996000.0, 500.0, 1829, 1332
os.makedirs(SC, exist_ok=True); os.makedirs(OUT, exist_ok=True)
