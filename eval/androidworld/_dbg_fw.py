import subprocess, time
import aw_env
from android_world.env import interface
from run_aw import REPO, _envoy_env
U2 = ("import uiautomator2 as u2, time; d = u2.connect('emulator-5560'); d.dump_hierarchy(); time.sleep(3); d.stop_uiautomator(); print('u2 ok')")
env = aw_env.connect()
w = env.controller.env
aw_env.park_forwarder(); time.sleep(1)
print(subprocess.run(["uv", "run", "--project", "backend", "python", "-c", U2], cwd=REPO, env=_envoy_env(), capture_output=True, text=True).stdout.strip())
print("after u2; bound:", aw_env.adb_shell("dumpsys accessibility | grep -c 'Bound services:{Service'"), aw_env.adb_shell("pidof", aw_env.FORWARDER), aw_env.adb_shell("ps -A | grep -c app_process"))
w._start_a11y_services(); time.sleep(2)
print("started; bound:", aw_env.adb_shell("dumpsys accessibility | grep -c 'Bound services:{Service'"), aw_env.adb_shell("pidof", aw_env.FORWARDER), aw_env.adb_shell("settings get secure enabled_accessibility_services"))
aw_env._send_grpc_port(w); w._enable_a11y_tree_logs(); time.sleep(2)
for i in range(5):
    w.step(interface._get_no_op_action())
    ex = w.accumulate_new_extras()
    print(i, "extras:", {k: len(v) for k, v in ex.items()})
    time.sleep(1)
print("dumpsys a11y:", aw_env.adb_shell("dumpsys accessibility | grep -E 'Bound services|Enabled services|UiAutomation|uiAutomation' | head -5"))
env.close()
