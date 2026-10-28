"""Finish the two onboarding steps AndroidWorld's automatic setup could not do on this emulator, then re-save those
apps' snapshots (AndroidWorld restores them before every task).

- contacts: setup looks for "Don't allow" (straight apostrophe); Android 13 here says "Don’t allow" (U+2019). Tapped by
  hand over adb (Oct 27); this re-saves the snapshot in that state.
- open tracks: setup's click on "Allow" found nothing (its permissions are already granted over adb), so its last steps,
  launching and closing "activity tracker", never ran. They run here, with AndroidWorld's own functions.
"""

import time

from android_world.env import adb_utils
from android_world.utils import app_snapshot

import aw_env

env = aw_env.connect()
adb_utils.launch_app("activity tracker", env.controller)
time.sleep(3)
adb_utils.close_app("activity tracker", env.controller)
for app in ("contacts", "open tracks sports tracker"):
    app_snapshot.save_snapshot(app, env.controller)
    print("saved snapshot:", app)
adb_utils.press_home_button(env.controller)
env.close()
