"""Offline tests on real SkyLark Air screens captured from envoy-test (tests/screens/*.xml)."""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest

from agent.checks import answer_tokens, evaluate
from agent.popups import match_popup
from devices.screen import PASSWORD_MASK, build_state, parse_hierarchy
from devices.types import Action, ScreenState
from models.schemas import PLAN_SCHEMA, STEP_SCHEMA, SuccessCheck, check_strict_subset
from policy.risk import classify
from policy.signin import sign_in_reason

SCREENS = Path(__file__).parent / "screens"


def screen(name: str) -> ScreenState:
    return build_state((SCREENS / f"{name}.xml").read_text(), "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400)


def el(s: ScreenState, rid: str) -> int:
    return next(e.number for e in s.numbered if e.resource_id == rid)


# ---- compact format -----------------------------------------------------------------------------

def test_info_rows_merge_into_one_line_with_id():
    s = screen("skylark_trip")
    gate = next(e for e in s.numbered if e.resource_id == "row_gate")
    assert gate.label == "Gate · B12"
    assert '[%d] Text "Gate · B12" (id: row_gate)' % gate.number in s.compact


def test_empty_compose_field_is_labeled_by_its_floating_label():
    s = screen("skylark_trip")
    ktn = next(e for e in s.numbered if e.resource_id == "field_ktn")
    assert ktn.label == "Known traveler number"
    assert "(empty)" in s.compact.splitlines()[ktn.number]


def test_status_bar_is_not_listed():
    s = screen("skylark_home")
    assert not any(e.status_bar for e in s.numbered)


# ---- risk ---------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, rid, expected",
    [
        ("skylark_confirm_checkin", "btn_confirm_checkin", "irreversible"),
        ("skylark_trip", "btn_checkin", "reversible"),  # only starts the flow
        ("skylark_trip", "btn_change_seat", "reversible"),
        ("skylark_bag_dialog", "btn_pay_bag", "irreversible"),
        ("skylark_bag_dialog", "btn_dialog_cancel", "reversible"),  # plain "Cancel" dismisses
        ("skylark_trip", "btn_cancel_trip", "irreversible"),
    ],
)
def test_rules_classify_taps(name, rid, expected):
    s = screen(name)
    v = classify(Action(kind="tap", element=el(s, rid)), s, model_risk="reversible")
    assert v.level == expected, v.reasons


def test_model_label_alone_can_force_approval():
    s = screen("skylark_trip")
    v = classify(Action(kind="tap", element=el(s, "btn_change_seat")), s, model_risk="irreversible")
    assert v.irreversible and v.reasons == ["model: labeled irreversible"]


def _buttons(*labels: str, package: str = "com.example.app", clickable: bool = True) -> ScreenState:
    """A screen of plain buttons (or, not clickable, plain texts), one per label, stacked down the page."""
    def node(i: int, label: str) -> str:
        top = 200 + i * 150
        cls = "android.widget.Button" if clickable else "android.widget.TextView"
        return (f'<node index="{i}" text={quoteattr(label)} resource-id="" class="{cls}" package="{package}" '
                f'content-desc="" checkable="false" checked="false" clickable="{str(clickable).lower()}" enabled="true" focusable="true" '
                'focused="false" scrollable="false" long-clickable="false" password="false" selected="false" '
                f'visible-to-user="true" bounds="[40,{top}][1040,{top + 120}]" drawing-order="{i}" hint="" display-id="0" />')
    xml = ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
           f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{package}" content-desc="" '
           'checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" '
           'scrollable="false" long-clickable="false" password="false" selected="false" visible-to-user="true" '
           'bounds="[0,0][1080,2400]" drawing-order="0" hint="" display-id="0">'
           + "".join(node(i, label) for i, label in enumerate(labels)) + "</node></hierarchy>")
    return build_state(xml, package, f"{package}.MainActivity", 1080, 2400)


@pytest.mark.parametrize("label", ["Share", "Post", "Publish", "Share now", "Post reel", "Share to your story"])
def test_a_button_that_publishes_is_irreversible_by_rule(label):
    """A public post can't be taken back, so the rules flag it without the model's label (Instagram's last screen is
    "Share")."""
    s = _buttons("Next", label)
    target = next(e for e in s.numbered if e.label == label)
    v = classify(Action(kind="tap", element=target.number), s, model_risk="reversible")
    assert v.irreversible and f"rule: target publishes {label!r}" in v.reasons


@pytest.mark.parametrize("label", ["Share your feedback", "Posts", "Post office hours", "Shared with you", "Republish settings"])
def test_publishing_words_inside_other_labels_are_not_flagged(label):
    s = _buttons(label)
    v = classify(Action(kind="tap", element=s.numbered[0].number), s, model_risk="reversible")
    assert not v.irreversible, v.reasons


@pytest.mark.parametrize("label", ["Schedule Order", "Schedule order · $23.46", "Schedule your order", "Place Order", "Finalize order"])
def test_a_button_that_commits_an_order_is_irreversible_by_rule(label):
    """An order spends money, so its button is flagged without the model's label, even on a screen that says nothing about
    payment (a closed store's checkout says "Schedule Order")."""
    s = _buttons("Back", label)
    target = next(e for e in s.numbered if e.label == label)
    v = classify(Action(kind="tap", element=target.number), s, model_risk="reversible")
    assert v.irreversible and f"rule: target says {label!r}" in v.reasons


@pytest.mark.parametrize("label", ["Schedule", "Order for later", "Order details", "Reorder", "Orders", "Scheduled orders"])
def test_order_words_that_commit_nothing_are_not_flagged(label):
    s = _buttons(label)
    v = classify(Action(kind="tap", element=s.numbered[0].number), s, model_risk="reversible")
    assert not v.irreversible, v.reasons


@pytest.mark.parametrize("label, app", [
    ("Request UberX", "com.example.app"), ("Request Lyft", "com.example.app"), ("Request Uber Black", "com.example.app"),
    ("Request a ride", "com.example.app"), ("Request pickup", "com.example.app"), ("Book ride", "com.example.app"),
    ("Schedule a ride", "com.example.app"), ("Request UberX · $23.40", "com.example.app"),
    ("Request Comfort", "com.ubercab"), ("Request XL", "com.ubercab"), ("Request Priority Pickup", "me.lyft.android"),
    ("Request Wait & Save", "me.lyft.android"), ("Request", "me.lyft.android"),
])
def test_a_button_that_requests_a_ride_is_irreversible_by_rule(label, app):
    """Requesting a ride charges for it and sends a driver, so its button is flagged without the model's label. In a ride app
    any button that starts with "Request" counts, since its products can't all be listed (loop B's Lyft fare estimates)."""
    s = _buttons("Back", label, package=app)
    target = next(e for e in s.numbered if e.label == label)
    v = classify(Action(kind="tap", element=target.number), s, model_risk="reversible")
    assert v.irreversible and f"rule: target requests a ride {label!r}" in v.reasons


def test_confirm_pickup_is_irreversible_by_rule():
    s = _buttons("Back", "Confirm pickup", package="com.ubercab")
    v = classify(Action(kind="tap", element=s.numbered[1].number), s, model_risk="reversible")
    assert v.irreversible and "rule: target says 'Confirm pickup'" in v.reasons


@pytest.mark.parametrize("label, app", [
    ("Request a feature", "com.example.app"), ("Request refund", "com.example.app"), ("Request desktop site", "com.android.chrome"),
    ("Ride history", "com.ubercab"), ("Ride details", "me.lyft.android"), ("Set pickup", "com.ubercab"),
    ("Choose a ride", "com.ubercab"), ("See prices", "me.lyft.android"), ("Schedule", "com.ubercab"), ("Requests", "me.lyft.android"),
])
def test_ride_words_that_request_nothing_are_not_flagged(label, app):
    s = _buttons(label, package=app)
    v = classify(Action(kind="tap", element=s.numbered[0].number), s, model_risk="reversible")
    assert not v.irreversible, v.reasons


@pytest.mark.parametrize("label", ["Request a ride", "Request UberX"])
def test_ride_words_on_a_text_that_is_not_a_button_are_not_flagged(label):
    s = _buttons(label, package="com.ubercab", clickable=False)
    assert s.numbered[0].kind == "Text"
    v = classify(Action(kind="tap", element=s.numbered[0].number), s, model_risk="reversible")
    assert not v.irreversible, v.reasons


def _dialog(package: str, question: str, *buttons: str) -> ScreenState:
    """A confirmation dialog as AndroidWorld recorded them (Oct 28): its text, then its buttons, the negative one first."""
    def node(i: int, cls: str, text: str, rid: str) -> str:
        top, clickable = 900 + i * 150, str(cls.endswith("Button")).lower()
        return (f'<node index="{i}" text={quoteattr(text)} resource-id="{rid}" class="{cls}" package="{package}" '
                f'content-desc="" checkable="false" checked="false" clickable="{clickable}" enabled="true" focusable="{clickable}" '
                'focused="false" scrollable="false" long-clickable="false" password="false" selected="false" '
                f'visible-to-user="true" bounds="[80,{top}][1000,{top + 120}]" drawing-order="{i}" hint="" display-id="0" />')
    kids = node(0, "android.widget.TextView", question, "android:id/message") + "".join(
        node(i + 1, "android.widget.Button", b, f"android:id/button{len(buttons) - i}") for i, b in enumerate(buttons))
    xml = ("<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">"
           f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{package}" content-desc="" '
           'checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" '
           'scrollable="false" long-clickable="false" password="false" selected="false" visible-to-user="true" '
           'bounds="[0,0][1080,2400]" drawing-order="0" hint="" display-id="0">' + kids + "</node></hierarchy>")
    return build_state(xml, package, f"{package}.MainActivity", 1080, 2400)


_DELETE_DIALOGS = [
    ("com.simplemobiletools.calendar.pro", "Are you sure you want to proceed with the deletion?", "No", "Yes"),
    ("com.google.android.documentsui", 'Delete "x.jpg"?', "CANCEL", "OK"),
    ("com.google.android.calendar", "Delete this event?", "Cancel", "OK"),
    ("com.google.android.apps.photos", "Delete 3 items?", "Cancel", "OK"),
]


@pytest.mark.parametrize("package, question, negative, affirmative", _DELETE_DIALOGS)
def test_the_affirmative_button_on_a_dialog_confirming_a_deletion_is_irreversible_by_code(package, question, negative, affirmative):
    """AndroidWorld (Oct 28): Simple Calendar's "Yes" on "…proceed with the deletion?" (31 taps) and Files' "OK" on
    'Delete "…"?' (6) were flagged only by the model's label: neither dialog says "want to delete" or that it can't be undone."""
    s = _dialog(package, question, negative, affirmative)
    yes = next(e for e in s.numbered if e.label == affirmative)
    for action in (Action(kind="tap", element=yes.number), Action(kind="tap_point", x=yes.center[0], y=yes.center[1])):
        v = classify(action, s, None)
        assert v.irreversible and v.reasons == ["screen: confirming a deletion"], v.reasons
    # Saying it outright was already enough.
    s = _dialog(package, "Permanently delete 3 items?", negative, affirmative)
    assert classify(Action(kind="tap", element=next(e for e in s.numbered if e.label == affirmative).number), s, None).irreversible


@pytest.mark.parametrize("package, question, negative, affirmative", _DELETE_DIALOGS)
def test_cancel_or_no_on_a_dialog_confirming_a_deletion_is_not_flagged(package, question, negative, affirmative):
    s = _dialog(package, question, negative, affirmative)
    v = classify(Action(kind="tap", element=next(e for e in s.numbered if e.label == negative).number), s, None)
    assert not v.irreversible, v.reasons


def test_a_screen_that_only_lists_delete_is_not_a_deletion_dialog():
    """A menu that offers "Delete", or a text that starts with it but asks nothing: its "Delete" is flagged by its own
    label, as before, and the rest stay plain taps."""
    s = _buttons("Open with", "Rename", "Delete", "Select all", "OK", package="com.google.android.documentsui")
    for e in s.numbered:
        v = classify(Action(kind="tap", element=e.number), s, None)
        assert v.reasons == (["rule: target says 'Delete'"] if e.label == "Delete" else []), (e.label, v.reasons)
    s = _dialog("com.google.android.apps.messaging", "Delete old messages automatically", "Cancel", "OK")
    assert not classify(Action(kind="tap", element=next(e for e in s.numbered if e.label == "OK").number), s, None).irreversible


_CHIPS = ("Show saved passwords and password options", "Show saved payment methods", "Show saved addresses")


def _chrome_with_keyboard(button: str, *page_text: str, package: str = "com.android.chrome",
                          accessory: str = "com.android.chrome:id/keyboard_accessory") -> ScreenState:
    """Chrome with a text field focused, as loop B saved it on Oct 30 (task-1030-143603-a850, Google Flights): the page (a
    field, a button, any text), and Chrome's keyboard accessory bar with its three "Show saved …" chips."""
    attrs = ('checkable="false" checked="false" enabled="true" focused="false" scrollable="false" long-clickable="false" '
             'password="false" selected="false" visible-to-user="true" hint="" display-id="0"')

    def node(cls: str, bounds: str, *, text: str = "", desc: str = "", rid: str = "", clickable: bool = False, kids: str = "") -> str:
        return (f'<node index="0" text={quoteattr(text)} resource-id="{rid}" class="{cls}" package="{package}" '
                f'content-desc={quoteattr(desc)} clickable="{str(clickable).lower()}" focusable="{str(clickable).lower()}" {attrs} '
                f'bounds="{bounds}"' + (f">{kids}</node>" if kids else " />"))

    page = (node("android.widget.EditText", "[40,300][1040,420]", text="JFK", clickable=True)
            + node("android.widget.Button", "[40,480][1040,640]", text=button, clickable=True)
            + "".join(node("android.widget.TextView", f"[40,{700 + i * 100}][1040,{780 + i * 100}]", text=t) for i, t in enumerate(page_text)))
    chips = "".join(node("android.widget.ImageButton", f"[{702 + i * 126},2018][{828 + i * 126},2144]", desc=c, clickable=True)
                    for i, c in enumerate(_CHIPS))
    bar = node("android.widget.LinearLayout", "[0,1976][1080,2165]", rid=accessory,
               desc="Alternative filling options available above the keyboard",
               kids=node("android.widget.LinearLayout", "[0,1997][1080,2165]", rid="com.android.chrome:id/accessory_bar_contents",
                         kids=node("androidx.recyclerview.widget.RecyclerView", "[0,1997][1080,2165]",
                                   rid="com.android.chrome:id/bar_items_view",
                                   kids=node("android.widget.LinearLayout", "[702,1997][1080,2165]", kids=chips))))
    root = node("android.widget.FrameLayout", "[0,0][1080,2400]", rid="android:id/content",
                kids=node("android.view.ViewGroup", "[0,0][1080,2400]", rid="com.android.chrome:id/coordinator",
                          kids=node("android.webkit.WebView", "[0,280][1080,1976]", kids=page) + bar))
    xml = "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\">" + root + "</hierarchy>"
    return build_state(xml, package, "com.google.android.apps.chrome.Main", 1080, 2400)


def test_chromes_show_saved_payment_methods_chip_does_not_make_a_page_a_checkout():
    """Chrome shows "Show saved payment methods" above the keyboard whenever a field has focus: every Chrome step with the
    keyboard up used to ask as a payment step (loop B, Google Flights: the JFK suggestion and a typed URL, both declined)."""
    s = _chrome_with_keyboard("John F. Kennedy International Airport (JFK)")
    assert {e.label for e in s.numbered} >= set(_CHIPS)
    jfk = next(e for e in s.numbered if e.label.startswith("John F. Kennedy"))
    v = classify(Action(kind="tap", element=jfk.number), s, model_risk="read")
    assert not v.irreversible, v.reasons


@pytest.mark.parametrize("page", ["Order total $12.40", "Payment method · Visa ending in 4242"])
def test_a_checkout_page_in_chrome_still_asks_with_the_keyboard_up(page):
    s = _chrome_with_keyboard("Continue", "Your order", page)
    btn = next(e for e in s.numbered if e.label == "Continue")
    v = classify(Action(kind="tap", element=btn.number), s, model_risk="read")
    assert v.irreversible and "screen: payment or final-confirmation step" in v.reasons


@pytest.mark.parametrize("where", [dict(package="com.example.browser"), dict(accessory="com.example:id/page_footer")])
def test_show_saved_payment_methods_anywhere_else_still_counts(where):
    """Only Chrome's own accessory bar is left out: the same words in another app, or outside the bar, still count."""
    s = _chrome_with_keyboard("John F. Kennedy International Airport (JFK)", **where)
    jfk = next(e for e in s.numbered if e.label.startswith("John F. Kennedy"))
    v = classify(Action(kind="tap", element=jfk.number), s, model_risk="read")
    assert "screen: payment or final-confirmation step" in v.reasons


def test_instagrams_publish_button_labelled_next_is_irreversible_by_its_id():
    """Instagram 453's reel screen publishes with a button labelled only "Next" (id share_button): the rules flag it by
    its id, so posting always asks. Recorded on the Pixel 5 by creator-workflow, Oct 29."""
    xml = (SCREENS / "instagram_reel_final.xml").read_text()
    s = build_state(xml, "com.instagram.android", "com.instagram.modal.ModalActivity", 1080, 2340)
    nxt = next(e for e in s.numbered if e.resource_id.endswith(("share_button", "share_button_container")))
    v = classify(Action(kind="tap", element=nxt.number), s, model_risk="reversible")
    assert v.irreversible and any("share_button" in r for r in v.reasons), v.reasons
    draft = next(e for e in s.numbered if e.label == "Save draft")
    assert not classify(Action(kind="tap", element=draft.number), s, model_risk="reversible").irreversible


def test_navigation_is_read():
    s = screen("skylark_trips")
    assert classify(Action(kind="scroll", direction="down"), s, model_risk="read").level == "read"


# ---- sign-in, pop-ups ---------------------------------------------------------------------------

def test_sign_in_screen_is_detected_and_others_are_not():
    assert sign_in_reason(screen("skylark_signin")) == "password field on screen"
    for name in ("skylark_home", "skylark_trip", "skylark_trips", "skylark_confirm_checkin"):
        assert sign_in_reason(screen(name)) is None, name


def test_a_filled_password_never_leaves_the_dump():
    """uiautomator2 dumps a filled password field's text as the password itself (Android 15, a saved login filled in):
    the compact view, the elements and the kept XML all carry a fixed mask instead, and the screen still reads as a sign-in."""
    xml = (SCREENS / "skylark_signin.xml").read_text()
    secret = "hunter2x9"
    filled = xml.replace('<node index="3" text="" resource-id="field_password"', f'<node index="3" text="{secret}" resource-id="field_password"')
    assert filled != xml
    s = build_state(filled, "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400)
    assert secret not in s.compact and secret not in s.raw_xml
    assert not any(secret in f"{e.text} {e.label}" for e in s.elements)
    assert not any(secret in e.text for e in parse_hierarchy(filled, 2400))  # read directly, too
    field = next(e for e in s.numbered if e.password)
    assert field.text == PASSWORD_MASK and "empty" not in s.compact.splitlines()[field.number]
    assert sign_in_reason(s) == "password field on screen"
    assert build_state(xml, "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400).raw_xml == xml  # nothing filled: untouched


def test_an_empty_password_field_showing_its_hint_still_reads_empty():
    """Android reports an empty field's text as its hint: that isn't a password, so it isn't masked and still reads empty."""
    xml = (SCREENS / "skylark_signin.xml").read_text()
    hinted = xml.replace('<node index="3" text="" resource-id="field_password"', '<node index="3" text="Password" resource-id="field_password"')
    hinted = hinted.replace('password="true" selected="false" visible-to-user="true" bounds="[42,801][1038,969]" drawing-order="3" hint=""',
                            'password="true" selected="false" visible-to-user="true" bounds="[42,801][1038,969]" drawing-order="3" hint="Password"')
    assert hinted.count('hint="Password"') == 1
    s = build_state(hinted, "com.skylark.air", "com.skylark.air.MainActivity", 1080, 2400)
    field = next(e for e in s.numbered if e.password)
    assert field.text == "Password" and PASSWORD_MASK not in s.compact
    assert "empty" in s.compact.splitlines()[field.number]


def test_rating_prompt_is_dismissed_without_a_model_call():
    pop = match_popup(screen("skylark_rating"), "check me in")
    assert pop is not None and pop.element.label == "Not now"
    assert match_popup(screen("skylark_rating"), "rate the app five stars") is None
    assert match_popup(screen("skylark_home"), "check me in") is None


# ---- success checks -----------------------------------------------------------------------------

def test_info_answer_must_be_visible():
    s = screen("skylark_trip")
    check = SuccessCheck(kind="info", value="gate", field_hint=None)
    assert evaluate(check, s, "Your gate is B12").passed
    assert not evaluate(check, s, "Gate C99").passed


def test_answer_tokens():
    assert "B12" in answer_tokens("Your gate is B12")
    assert answer_tokens("38,240 miles") == ["38,240"]


def test_text_visible_check():
    s = screen("skylark_confirm_checkin")
    assert evaluate(SuccessCheck(kind="text_visible", value="Confirm check-in", field_hint=None), s, "").passed
    assert not evaluate(SuccessCheck(kind="text_visible", value="You're checked in", field_hint=None), s, "").passed


def test_schemas_fit_metas_strict_subset():
    assert check_strict_subset(STEP_SCHEMA) == []
    assert check_strict_subset(PLAN_SCHEMA) == []
