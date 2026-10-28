"""The phone's apps by the names people use, so the agent can open "Simple Calendar Pro" or "Files" without knowing
their packages (any phone).

People name apps by their label; Envoy's `launch` took a package name, so the agent guessed packages
(`com.google.android.apps.nbu.files` for a phone whose Files app is `com.google.android.documentsui`) or went looking
through the launcher, which cost AndroidWorld runs most of their step budget (docs/androidworld-results.md).

- The launchable apps come from the phone (`cmd package query-activities` for MAIN/LAUNCHER): package and activity.
- Labels are read once per app version from the app's own APK (`adb pull` of its base APK, then the SDK's `aapt2 dump
  badging` on the Mac), cached in data/apps/labels.json by package and versionCode. A real phone could have hundreds of
  apps; only launchable ones are read, and only once per version.
- `resolve(name)` matches a spoken name against labels first and package words second, so "Simple Calendar Pro" picks
  com.simplemobiletools.calendar.pro over Google's Calendar, and a wrong package guess still finds the app by its words.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parents[2]
CACHE = REPO / "data" / "apps" / "labels.json"
_PKG = re.compile(r"^[A-Za-z][\w]*(\.[A-Za-z_][\w]*)+$")


@dataclass(frozen=True)
class AppEntry:
    label: str
    package: str
    activity: str  # component for `am start -n`, e.g. com.android.settings/.Settings


def looks_like_package(s: str) -> bool:
    return bool(_PKG.match(s.strip()))


def parse_launchers(text: str) -> list[tuple[str, str]]:
    """`cmd package query-activities --brief -a MAIN -c LAUNCHER` → [(package, component)], first activity per package."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if "/" in line and " " not in line:
            pkg = line.split("/", 1)[0]
            out.setdefault(pkg, line)
    return list(out.items())


def parse_versions(text: str) -> dict[str, str]:
    """`cmd package list packages --show-versioncode` → {package: versionCode}."""
    out = {}
    for line in text.splitlines():
        m = re.match(r"package:(\S+)\s+versionCode:(\d+)", line.strip())
        if m:
            out[m.group(1)] = m.group(2)
    return out


def parse_label(badging: str) -> str | None:
    """`aapt2 dump badging` output → the app's label (application-label, else the launchable activity's)."""
    for key in ("application-label", "application-label-en", "application-label-en-US"):
        m = re.search(rf"^{key}:'(.*)'$", badging, re.M)
        if m and m.group(1):
            return m.group(1)
    m = re.search(r"^launchable-activity: .*label='([^']+)'", badging, re.M)
    return m.group(1) if m else None


def _tokens(s: str) -> list[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)  # OpenTracks → Open Tracks
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


_FILLER = {"app", "the", "application", "android", "com", "org", "net", "google", "apps"}


def score(name: str, app: AppEntry) -> float:
    """How well a spoken app name fits an app: label words count double, words found in the package once,
    plus a bonus when the whole label is said."""
    q = [t for t in _tokens(name) if t not in _FILLER] or _tokens(name)
    if not q:
        return 0.0
    label = set(_tokens(app.label))
    pkg = app.package.lower()
    pts = sum(2.0 if t in label else 1.0 if len(t) > 2 and t in pkg else 0.0 for t in q) / len(q)
    said = "".join(_tokens(name))
    if label and all(t in said for t in label):
        pts += 1.0
    return pts


def resolve(name: str, apps: list[AppEntry]) -> AppEntry | None:
    """The app a name refers to, or None when nothing fits or two apps fit equally well."""
    name = name.strip()
    by_pkg = {a.package: a for a in apps}
    if name in by_pkg:
        return by_pkg[name]
    if looks_like_package(name):  # a guessed package that isn't installed: use its words ("…nbu.files" → Files)
        name = " ".join(p for p in name.split(".")[1:])
    ranked = sorted(((score(name, a), a) for a in apps), key=lambda t: -t[0])
    if not ranked or ranked[0][0] < 1.0:
        return None
    if len(ranked) > 1 and ranked[1][0] == ranked[0][0] and ranked[1][1].package != ranked[0][1].package:
        return None
    return ranked[0][1]


class AppIndex:
    """Launchable apps on one device. `shell(cmd)` runs an adb shell command; `pull(remote, local)` copies a file."""

    def __init__(self, shell: Callable[[str], str], pull: Callable[[str, str], None], cache: Path = CACHE,
                 aapt2: str | None = None) -> None:
        self.shell, self.pull, self.cache = shell, pull, cache
        self.aapt2 = aapt2 or _find_aapt2()
        self.apps: list[AppEntry] = []
        self.errors: dict[str, str] = {}  # package → why its label couldn't be read this time (not cached: retried next load)

    def _labels(self) -> dict[str, str]:
        return json.loads(self.cache.read_text()) if self.cache.exists() else {}

    def _label_of(self, package: str) -> str | None:
        paths = [l.split(":", 1)[1].strip() for l in self.shell(f"pm path {package}").splitlines() if l.startswith("package:")]
        base = next((p for p in paths if p.endswith("base.apk")), paths[0] if paths else None)
        if not base or not self.aapt2:
            raise RuntimeError("no APK path" if not base else "aapt2 not found in the Android SDK's build-tools")
        with tempfile.TemporaryDirectory() as d:
            local = os.path.join(d, "app.apk")
            self.pull(base, local)
            out = subprocess.run([self.aapt2, "dump", "badging", local], capture_output=True, text=True, timeout=60)
        return parse_label(out.stdout)

    def load(self) -> list[AppEntry]:
        launchers = parse_launchers(self.shell("cmd package query-activities --brief -a android.intent.action.MAIN "
                                               "-c android.intent.category.LAUNCHER"))
        versions = parse_versions(self.shell("cmd package list packages --show-versioncode"))
        labels = self._labels()
        changed = False
        apps = []
        for pkg, comp in launchers:
            key = f"{pkg}@{versions.get(pkg, '?')}"
            if not labels.get(key):
                try:
                    label = self._label_of(pkg)
                except Exception as e:  # noqa: BLE001 - an unreadable APK just has no label; its package words still match
                    self.errors[pkg] = f"{type(e).__name__}: {e}"[:200]
                    label = None
                if label:
                    labels[key] = label
                    changed = True
            apps.append(AppEntry(labels.get(key) or pkg.rsplit(".", 1)[-1], pkg, comp))
        if changed:
            self.cache.parent.mkdir(parents=True, exist_ok=True)
            self.cache.write_text(json.dumps(labels, indent=1, sort_keys=True))
        self.apps = sorted(apps, key=lambda a: a.label.lower())
        return self.apps

    def resolve(self, name: str) -> AppEntry | None:
        return resolve(name, self.apps or self.load())

    def listing(self) -> str:
        """One line for the planner: every launchable app by label, with its package where two share a label."""
        apps = self.apps or self.load()
        dup = {a.label for a in apps if sum(b.label == a.label for b in apps) > 1}
        return ", ".join(f"{a.label} ({a.package})" if a.label in dup else a.label for a in apps)

    def to_json(self) -> list[dict]:
        return [asdict(a) for a in self.apps]


def _find_aapt2() -> str | None:
    # ANDROID_HOME may come from a .env file with an unexpanded "~" (no shell to expand it), or be unset (android_env
    # deletes it from the process environment): expand it, and fall back to the SDK's default place on a Mac.
    for sdk in (os.environ.get("ANDROID_HOME"), Path.home() / "Library/Android/sdk"):
        found = sorted((Path(sdk).expanduser() / "build-tools").glob("*/aapt2")) if sdk else []
        if found:
            return str(found[-1])
    return None
