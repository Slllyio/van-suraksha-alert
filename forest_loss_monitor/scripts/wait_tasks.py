"""Block until this pipeline's EE tasks with a prefix leave READY/RUNNING. Usage: wait_tasks.py prefix [max_hours]"""
import sys
import time
import collections

import ee

from common import init

init()
prefix = sys.argv[1]
limit = time.time() + 3600 * (float(sys.argv[2]) if len(sys.argv) > 2 else 6)
while time.time() < limit:
    try:
        ts = [x for x in ee.data.getTaskList() if x["description"].startswith(prefix)]
    except Exception as e:
        print("retry", e, flush=True)
        time.sleep(120)
        continue
    c = collections.Counter(x["state"] for x in ts)
    if not (c["READY"] or c["RUNNING"]):
        break
    time.sleep(120)
print(c)
print("eecu_h %.1f" % (sum(x.get("batch_eecu_usage_seconds", 0) for x in ts) / 3600))
for x in ts:
    if x["state"] == "FAILED":
        print(x["description"], x.get("error_message", "")[:300])
