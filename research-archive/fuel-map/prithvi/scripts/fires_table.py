"""Fire table for the Prithvi tests: the big-fire early-warning set (research/fuel-from-heat h18) with first-pass dot positions.
Out: scratch fires.parquet (one row per fire) and dots.parquet (first-pass dots: fire, x, y)."""
import sys, os
sys.dont_write_bytecode = True
sys.path.insert(0, '/mnt/project-files/research/fuel-from-heat/scripts')
src = open('/mnt/project-files/research/fuel-from-heat/scripts/h18_bigfire_warning.py').read().split('SETS = {')[0]
exec(src)
SP = '/tmp/claude-0/-home-user/d4594ebc-4c67-5b87-9e36-c2f8e01f7c08/scratchpad'
G.to_parquet(f'{SP}/fires.parquet'); fp[['fire', 'x', 'y']].to_parquet(f'{SP}/dots.parquet')
print(G.shape, G.season.value_counts().sort_index().to_dict(), G.big.sum())
