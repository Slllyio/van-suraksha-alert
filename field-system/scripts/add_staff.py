"""Add a person who can sign in. PINs are asked for, never stored in plain text.

  python scripts/add_staff.py --name "R. Sharma" --role admin
  python scripts/add_staff.py --name "Beat guard" --role guard --beat 012-007-009
  python scripts/add_staff.py --name "Range officer" --role ranger --range Raisen:Obedullaganj
PIN: 4 to 12 digits. A range is 'Division:Range' when its name is used in more than one division.
Give each person the staff id printed at the end: they sign in with it and the PIN.
"""
import argparse, getpass, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import db
from app.geo import Beats
from app.server import hash_pin

ap = argparse.ArgumentParser()
ap.add_argument("--name", required=True)
ap.add_argument("--role", required=True, choices=["guard", "ranger", "admin"])
ap.add_argument("--beat")
ap.add_argument("--range")
ap.add_argument("--phone")
ap.add_argument("--pin", help="omit to be asked")
a = ap.parse_args()
pin = a.pin or getpass.getpass("PIN for %s: " % a.name)
if not (pin.isdigit() and 4 <= len(pin) <= 12):
    sys.exit("PIN must be 4 to 12 digits")
B = Beats()
if a.role == "guard" and a.beat not in B.by_uid:
    sys.exit("unknown beat uid %r" % a.beat)
if a.role == "ranger" and len({B.by_uid[u].get("division") for u in B.in_range(a.range)}) != 1:
    sys.exit("range %r not found, or used in more than one division: give it as Division:Range" % a.range)
db.init()
with db.tx() as con:
    cur = con.execute("INSERT INTO staff(name,role,beat_uid,range_name,phone,pin_hash) VALUES (?,?,?,?,?,?)",
                      (a.name, a.role, a.beat, a.range, a.phone, hash_pin(pin)))
print("added staff id", cur.lastrowid)
