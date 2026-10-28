"""Opening apps by the names people use (devices/apps.py): parsing the phone's launcher list and APK labels, and
matching a spoken name to one app, offline."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from devices.android import AndroidDevice
from devices.apps import AppEntry, AppIndex, looks_like_package, parse_label, parse_launchers, parse_versions, resolve
from models.prompts import plan_input

APPS = [AppEntry(label, pkg, f"{pkg}/.Main") for label, pkg in [
    ("Audio Recorder", "com.dimowner.audiorecorder"), ("Broccoli", "com.flauschcode.broccoli"),
    ("Calendar", "com.google.android.calendar"), ("Calendar", "com.simplemobiletools.calendar.pro"),
    ("Camera", "com.android.camera2"), ("Chrome", "com.android.chrome"), ("Clock", "com.google.android.deskclock"),
    ("Contacts", "com.google.android.contacts"), ("Draw", "com.simplemobiletools.draw.pro"),
    ("Files", "com.google.android.documentsui"), ("Gallery", "com.simplemobiletools.gallery.pro"),
    ("Joplin", "net.cozic.joplin"), ("Markor", "net.gsantner.markor"), ("OpenTracks", "de.dennisguse.opentracks"),
    ("OsmAnd", "net.osmand"), ("Pro Expense", "com.arduia.expense"), ("Retro", "code.name.monkey.retromusic"),
    ("Settings", "com.android.settings"), ("SMS Messenger", "com.simplemobiletools.smsmessenger"),
    ("Tasks", "org.tasks"), ("VLC", "org.videolan.vlc"),
]]


def pkg(name: str) -> str | None:
    a = resolve(name, APPS)
    return a.package if a else None


def test_names_people_use():
    assert pkg("Simple Calendar Pro") == "com.simplemobiletools.calendar.pro"
    assert pkg("Pro Expense") == "com.arduia.expense"
    assert pkg("pro expense") == "com.arduia.expense"
    assert pkg("Broccoli app") == "com.flauschcode.broccoli"
    assert pkg("open tracks sports tracker") == "de.dennisguse.opentracks"
    assert pkg("Retro Music") == "code.name.monkey.retromusic"
    assert pkg("Simple SMS Messenger") == "com.simplemobiletools.smsmessenger"
    assert pkg("Simple Draw Pro") == "com.simplemobiletools.draw.pro"
    assert pkg("Simple Gallery Pro") == "com.simplemobiletools.gallery.pro"
    assert pkg("Files") == "com.google.android.documentsui"
    assert pkg("Audio Recorder") == "com.dimowner.audiorecorder"
    assert pkg("Settings") == "com.android.settings"


def test_packages_exact_or_guessed():
    assert pkg("com.android.settings") == "com.android.settings"
    assert pkg("com.google.android.apps.nbu.files") == "com.google.android.documentsui"  # a wrong guess, found by its words
    assert looks_like_package("net.gsantner.markor") and not looks_like_package("Markor")


def test_ambiguous_or_unknown_names_resolve_to_nothing():
    assert pkg("Calendar") is None  # two apps are called Calendar: the caller must say which
    assert pkg("Spotify") is None
    assert pkg("") is None


def test_parsers():
    launchers = parse_launchers("36 activities found:\n  Activity #0:\n    priority=0 preferredOrder=0 match=0x108000\n"
                                "    com.android.camera2/com.android.camera.CameraLauncher\n  Activity #1:\n"
                                "    com.android.settings/.Settings\n    com.android.settings/.Other\n")
    assert launchers == [("com.android.camera2", "com.android.camera2/com.android.camera.CameraLauncher"),
                         ("com.android.settings", "com.android.settings/.Settings")]
    assert parse_versions("package:org.tasks versionCode:130805\npackage:net.osmand versionCode:4\n") == {"org.tasks": "130805", "net.osmand": "4"}
    assert parse_label("package: name='x'\napplication-label:'Pro Expense'\nlaunchable-activity: name='a' label='Other'") == "Pro Expense"
    assert parse_label("launchable-activity: name='a'  label='Joplin' icon=''") == "Joplin"


def test_index_reads_labels_once_per_app_version(tmp_path):
    calls = []

    def shell(cmd: str) -> str:
        calls.append(cmd)
        if "query-activities" in cmd:
            return "    com.arduia.expense/.MainActivity\n    org.tasks/.Main\n"
        if "list packages" in cmd:
            return "package:com.arduia.expense versionCode:7\npackage:org.tasks versionCode:9\n"
        return f"package:/data/app/{cmd.split()[-1]}/base.apk\n"

    idx = AppIndex(shell, lambda remote, local: None, cache=tmp_path / "labels.json", aapt2="true")
    idx._label_of = lambda p: {"com.arduia.expense": "Pro Expense", "org.tasks": "Tasks"}[p]  # type: ignore[method-assign]
    assert [a.label for a in idx.load()] == ["Pro Expense", "Tasks"]
    again = AppIndex(shell, lambda remote, local: None, cache=tmp_path / "labels.json", aapt2="true")
    again._label_of = lambda p: (_ for _ in ()).throw(AssertionError("cached"))  # type: ignore[method-assign]
    assert again.resolve("Pro Expense").activity == "com.arduia.expense/.MainActivity"
    assert again.listing() == "Pro Expense, Tasks"


def test_a_label_that_cant_be_read_is_retried_not_cached(tmp_path):
    def shell(cmd: str) -> str:
        if "query-activities" in cmd:
            return "    com.google.android.documentsui/.Files\n"
        if "list packages" in cmd:
            return "package:com.google.android.documentsui versionCode:3\n"
        return "package:/system/priv-app/DocumentsUIGoogle/DocumentsUIGoogle.apk\n"

    idx = AppIndex(shell, lambda remote, local: None, cache=tmp_path / "labels.json", aapt2="true")
    idx._label_of = lambda p: (_ for _ in ()).throw(OSError("pull failed"))  # type: ignore[method-assign]
    assert idx.listing() == "documentsui" and idx.errors == {"com.google.android.documentsui": "OSError: pull failed"}
    again = AppIndex(shell, lambda remote, local: None, cache=tmp_path / "labels.json", aapt2="true")
    again._label_of = lambda p: "Files"  # type: ignore[method-assign]
    assert again.resolve("Files").package == "com.google.android.documentsui" and not again.errors


def test_aapt2_is_found_when_android_home_has_a_tilde_or_is_wrong(tmp_path, monkeypatch):
    from devices.apps import _find_aapt2

    tool = tmp_path / "Library/Android/sdk/build-tools/37.0.0/aapt2"
    tool.parent.mkdir(parents=True)
    tool.write_text("")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("ANDROID_HOME", "~/Library/Android/sdk")  # as a .env file writes it: no shell expands the "~"
    assert _find_aapt2() == str(tool)
    monkeypatch.setenv("ANDROID_HOME", str(tmp_path / "nowhere"))
    assert _find_aapt2() == str(tool)
    monkeypatch.delenv("ANDROID_HOME")  # android_env deletes it
    assert _find_aapt2() == str(tool)


def device_with(apps):
    d = AndroidDevice("emulator-test")
    shell = []
    d.adb = SimpleNamespace(shell=lambda cmd: shell.append(cmd) or ("No activity found" if "resolve-activity" in str(cmd) else ""))
    idx = AppIndex(lambda c: "", lambda r, l: None, aapt2="true")
    idx.apps = apps
    d._apps = idx
    return d, shell


def test_apps_open_by_name_or_by_a_wrong_package_guess():
    d, shell = device_with(APPS)
    d._launch("Simple Calendar Pro")
    assert shell[-1] == ["am", "start", "-n", "com.simplemobiletools.calendar.pro/.Main"]
    d._launch("com.google.android.apps.nbu.files")  # not installed: found by its words
    assert shell[-1] == ["am", "start", "-n", "com.google.android.documentsui/.Main"]
    with pytest.raises(RuntimeError, match=r"Apps: Audio Recorder"):
        d._launch("Calendar")  # two apps are called Calendar: the error lists the phone's apps


def test_the_plan_sees_the_phones_apps():
    text = plan_input("Open Pro Expense", "App: launcher", apps="Files, Pro Expense")
    assert "APPS ON THIS PHONE:\nFiles, Pro Expense" in text
    assert "APPS ON THIS PHONE" not in plan_input("Open Pro Expense", "App: launcher")
