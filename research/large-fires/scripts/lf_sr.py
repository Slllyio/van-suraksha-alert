"""Re-use the round-22 system_rebuild feature code (ratapani/fsi/scouting/code/system_rebuild) on all 87 divisions,
with its scratch caches pointed at this study's scratch. Import this before features/common of system_rebuild."""
import os, sys
os.environ['R22_SUB'] = '0'
import lf_common as L
sys.path.insert(0, L.P + 'ratapani/fsi/scouting/code/system_rebuild')
import common as C
C.SC = L.SC + 'r22/'; os.makedirs(C.SC, exist_ok=True)
import features as Fe
