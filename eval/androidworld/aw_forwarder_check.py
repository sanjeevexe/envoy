"""Check the forwarder park/restore around a uiautomator2 session: no crash dialog, AndroidWorld reads the screen after,
and the restore changes nothing else on the phone (Wi-Fi and airplane mode are left as the agent left them).

  eval/androidworld/aw.sh aw_forwarder_check.py [--no-park] [--wifi-off]
"""

import subprocess
import sys
import time

import aw_env
from run_aw import REPO, _envoy_env

U2 = ("import uiautomator2 as u2, time; d = u2.connect('emulator-5560'); d.dump_hierarchy(); time.sleep(8); "
      "d.dump_hierarchy(); d.stop_uiautomator(); print('u2 ok')")


def radios() -> str:
    return (f"wifi_on={aw_env.adb_shell('settings', 'get', 'global', 'wifi_on')} "
            f"airplane={aw_env.adb_shell('settings', 'get', 'global', 'airplane_mode_on')}")


env = aw_env.connect()
print("before:", len(env.get_state().ui_elements), "elements;", radios())
park = "--no-park" not in sys.argv
if park:
    aw_env.park_forwarder()
if "--wifi-off" in sys.argv:
    aw_env.adb_shell("svc", "wifi", "disable")
    time.sleep(2)
out = subprocess.run(["uv", "run", "--project", "backend", "python", "-c", U2], cwd=REPO, env=_envoy_env(), capture_output=True, text=True)
print(out.stdout.strip() or out.stderr[-500:])
time.sleep(2)
print("after u2: dialog:", aw_env.crash_dialog() or "none;", radios())
if park:
    print(f"restored in {aw_env.restore_forwarder(env):.1f} s;", radios())
print("after restore:", len(env.get_state().ui_elements), "elements; dialog:", aw_env.crash_dialog() or "none;", radios())
if "--wifi-off" in sys.argv:
    aw_env.adb_shell("svc", "wifi", "enable")
env.close()
