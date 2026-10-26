"""Turn the model's action (models.schemas) into a device action (devices.types)."""

from __future__ import annotations

from devices.types import Action, ScreenState
from models import schemas as s


def _px(v: int, size: int) -> int:
    """Meta's 0-1000 grid → device pixels (values can come back as 1001, so clamp)."""
    return round(min(1000, max(0, v)) * size / 1000)


def to_device_action(a: s.AgentAction, screen: ScreenState) -> Action | None:
    """None for actions the runtime handles itself: look, ask_user, handoff, done, fail."""
    w, h = screen.width, screen.height
    match a:
        case s.Tap():
            return Action(kind="tap", element=a.element)
        case s.LongPress():
            return Action(kind="long_press", element=a.element)
        case s.TypeText():
            return Action(kind="type", element=a.element, text=a.text, submit=a.submit)
        case s.Scroll():
            return Action(kind="scroll", direction=a.direction, element=a.element)
        case s.Swipe():
            return Action(kind="swipe", x=_px(a.from_x, w), y=_px(a.from_y, h), x2=_px(a.to_x, w), y2=_px(a.to_y, h))
        case s.Back():
            return Action(kind="back")
        case s.Home():
            return Action(kind="home")
        case s.Launch():
            return Action(kind="launch", package=a.app)
        case s.TapPoint():
            return Action(kind="tap_point", x=_px(a.x, w), y=_px(a.y, h))
        case s.Wait():
            return Action(kind="wait", seconds=min(10.0, max(0.0, a.seconds)))
    return None
