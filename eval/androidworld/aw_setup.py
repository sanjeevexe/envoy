"""AndroidWorld's setup on our emulator: installs its apps and data and saves each app's snapshot (run.py
--perform_emulator_setup), then the two onboarding steps it misses on this image (aw_env.finish_setup).

  eval/androidworld/aw.sh aw_setup.py            # setup, if the app snapshots are missing (first run, or after any reboot)
  eval/androidworld/aw.sh aw_setup.py --force    # setup again regardless
  eval/androidworld/aw.sh aw_setup.py --check    # connect only: proves the env, the token and the a11y forwarder

Android deletes AndroidWorld's snapshot directory on every boot (aw_env), so run_aw.py checks and calls this setup too.
"""

import sys
import time

import aw_env

t0 = time.time()
env = aw_env.connect()
if "--force" in sys.argv:
    from android_world.env import env_launcher

    env_launcher.setup_env(env, emulator_setup=True, freeze_datetime=True)
    aw_env.finish_setup(env)
elif "--check" not in sys.argv:
    aw_env.ensure_setup(env)
state = env.get_state(wait_to_stabilize=False)
print(f"ready in {time.time() - t0:.0f} s; screen {state.pixels.shape}, {len(state.ui_elements)} UI elements via the a11y forwarder;"
      f" {aw_env.snapshot_count()} app snapshots; foreground {env.foreground_activity_name}; AndroidWorld {aw_env.aw_commit()[:12]}")
env.close()
