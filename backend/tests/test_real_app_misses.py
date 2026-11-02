"""Real-app misses from the Nov 2 baseline (run 1102175459 on 192cd29, envoy-real), each traced to the compiler.

- amazon's reruns waited on a check for a heads-up notification (CapCut's "An amazing template for you!") that was drawn over
  Amazon's start screen when the run was recorded. Checks on System UI drawn over the app are no longer compiled.
- chrome_wikipedia's agent found the article already open (Chrome restores its last tab), so its topic was never typed and the
  compiler dropped the input: the routine answered 1889 for any topic. The input now stays, as a check on the start screen.

The screens are small made-up ones with each app's shape (the real trees stay out of the repo).
"""

from __future__ import annotations


from routines.compiler import _passing
from routines.model import Check, Locator
from routines.screens import screen_from_tree


def _screen(package: str, elements: list[dict]):
    return screen_from_tree({"package": package, "activity": "Main", "width": 1080, "height": 2400, "elements": elements})


def _el(i: int, rid: str, label: str, kind: str = "Button", parent: int | None = None, number: int | None = None, **kw) -> dict:
    return {"index": i, "parent": parent, "number": number, "resource_id": rid, "label": label, "text": label, "kind": kind,
            "bounds": [0, 100 * i, 1080, 100 * i + 90], **kw}


AMAZON = "com.amazon.mShop.android.shopping"
HOME = _screen(AMAZON, [
    _el(0, "com.android.systemui:id/expandableNotificationRow", "CapCut · An amazing template for you!", number=1),
    _el(1, "android:id/notification_headerless_view_column", "An amazing template for you!", "Text", parent=0, number=2),
    _el(2, f"{AMAZON}:id/chrome_search_hint_view", "Search Amazon", "Text", number=3),
])


def test_a_check_on_a_notification_drawn_over_the_app_is_not_compiled():
    over = Check(kind="element_present", locator=Locator(resource_id="notification_headerless_view_column",
                                                         text="An amazing template for you!", kind="Text"))
    assert _passing(over, HOME, None, {}) == "a system notification drawn over the app"
    own = Check(kind="element_present", locator=Locator(resource_id="chrome_search_hint_view", text="Search Amazon", kind="Text"))
    assert _passing(own, HOME, None, {}) is None

