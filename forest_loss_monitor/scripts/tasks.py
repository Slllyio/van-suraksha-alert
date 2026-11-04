"""Print this pipeline's EE export tasks. Usage: tasks.py [prefix]"""
import sys
import collections

import ee

from common import init

init()
prefix = sys.argv[1] if len(sys.argv) > 1 else "flm_"
ts = [x for x in ee.data.getTaskList() if x["description"].startswith(prefix)]
print(collections.Counter(x["state"] for x in ts))
for x in ts[:12]:
    print(x["description"], x["state"], "eecu_h=%.2f" % (x.get("batch_eecu_usage_seconds", 0) / 3600), x.get("error_message", "")[:200])
print("total eecu_h %.1f" % (sum(x.get("batch_eecu_usage_seconds", 0) for x in ts) / 3600))
