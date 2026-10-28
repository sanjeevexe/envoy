"""Check that parking AndroidWorld's forwarder while uiautomator2 runs avoids its crash, and that it reads the screen after.

  eval/androidworld/aw.sh aw_forwarder_check.py [--no-park]
"""

import subprocess
import sys
import time

import aw_env
from run_aw import REPO, _envoy_env

U2 = ("import uiautomator2 as u2, time; d = u2.connect('emulator-5560'); d.dump_hierarchy(); time.sleep(8); "
      "d.dump_hierarchy(); d.stop_uiautomator(); print('u2 ok')")

env = aw_env.connect()
print("before:", len(env.get_state().ui_elements), "elements; dialog:", aw_env.crash_dialog() or "none")
park = "--no-park" not in sys.argv
if park:
    aw_env.park_forwarder()
out = subprocess.run(["uv", "run", "--project", "backend", "python", "-c", U2], cwd=REPO, env=_envoy_env(), capture_output=True, text=True)
print(out.stdout.strip() or out.stderr[-500:])
time.sleep(3)
print("after u2:", "dialog:", aw_env.crash_dialog() or "none")
if park:
    print(f"restored in {aw_env.restore_forwarder(env):.1f} s")
print("after restore:", len(env.get_state().ui_elements), "elements; dialog:", aw_env.crash_dialog() or "none")
env.close()
