"""One-time AndroidWorld setup on our emulator: installs its 20 apps and their data (run.py --perform_emulator_setup).

  eval/androidworld/aw.sh aw_setup.py            # one-time setup (several minutes)
  eval/androidworld/aw.sh aw_setup.py --check    # connect only: proves the env, the token and the a11y forwarder
"""

import sys
import time

import aw_env

t0 = time.time()
env = aw_env.connect(emulator_setup="--check" not in sys.argv)
state = env.get_state(wait_to_stabilize=False)
print(f"connected in {time.time() - t0:.0f} s; screen {state.pixels.shape}, {len(state.ui_elements)} UI elements via the a11y forwarder;"
      f" foreground {env.foreground_activity_name}; AndroidWorld {aw_env.aw_commit()[:12]}")
env.close()
