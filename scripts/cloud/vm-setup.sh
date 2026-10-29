#!/usr/bin/env bash
# Runs ON the VM (scripts/cloud/setup.sh copies it there with its files): the toolchain and the envoy-test AVD.
#
# Installs JDK 21, the Android command-line tools 23.0 (pinned, checksum-checked), platform-tools, the emulator,
# android-35 google_apis_playstore x86_64, uv 0.13.5 with Python 3.13, and an AVD named envoy-test with the Mac
# envoy-test's hardware (envoy-test.config.ini: 1080x2400, 420 dpi, 4 GB, Play Store), but an x86_64 image.
# The SDK lives in ~/android-sdk, linked as ~/Library/Android/sdk so scripts/env.sh's Mac path works unchanged.
# Also installs envoy-idle-stop: the VM powers itself off after ~45 idle minutes (no SSH session, no Envoy run, no
# client on the API, no keep-awake).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SDK="$HOME/android-sdk"
IMAGE="system-images;android-35;google_apis_playstore;x86_64"
CMDLINE_ZIP="commandlinetools-linux-16111833_latest.zip"   # cmdline-tools 23.0, the Mac's version
CMDLINE_SHA1="e025545c62a8e64c7559119566a569fb1dec5f60"     # from dl.google.com/android/repository/repository2-3.xml
UV_VERSION="0.13.5"                                         # the Mac's version

echo "== packages"
sudo DEBIAN_FRONTEND=noninteractive apt-get update -q
sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq --no-install-recommends \
  openjdk-21-jdk-headless unzip curl git cpu-checker ca-certificates \
  libpulse0 libnss3 libxcomposite1 libxcursor1 libxdamage1 libxi6 libxtst6 libxrandr2 libxkbfile1 libxkbcommon0 \
  libgl1 libegl1 libgbm1 libdrm2 libasound2t64 libdbus-1-3 libfontconfig1 libx11-xcb1 >/dev/null

echo "== KVM"
[ -e /dev/kvm ] || { echo "no /dev/kvm: nested virtualization is off on this VM; stop here (no software emulation)" >&2; exit 1; }
kvm-ok || true
sudo usermod -aG kvm "$USER"
sudo loginctl enable-linger "$USER"  # keeps /run/user/<uid> (the emulator's discovery folder) between SSH sessions

echo "== Android SDK"
if [ ! -x "$SDK/cmdline-tools/latest/bin/sdkmanager" ]; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/$CMDLINE_ZIP" "https://dl.google.com/android/repository/$CMDLINE_ZIP"
  echo "$CMDLINE_SHA1  $tmp/$CMDLINE_ZIP" | sha1sum -c -
  mkdir -p "$SDK/cmdline-tools"
  unzip -q "$tmp/$CMDLINE_ZIP" -d "$tmp"
  rm -rf "$SDK/cmdline-tools/latest" && mv "$tmp/cmdline-tools" "$SDK/cmdline-tools/latest"
  rm -rf "$tmp"
fi
# The licenses the user already accepted on the Mac (setup.sh copies $ANDROID_HOME/licenses), so nothing is accepted here.
mkdir -p "$SDK/licenses" && cp "$HERE"/licenses/* "$SDK/licenses/"
mkdir -p "$HOME/Library/Android" && ln -sfn "$SDK" "$HOME/Library/Android/sdk"
cp "$HERE/env-linux.sh" "$HOME/env-linux.sh"
source "$HOME/env-linux.sh"
sdkmanager --install "platform-tools" "emulator" "$IMAGE" >/dev/null

echo "== uv and Python 3.13"
if ! command -v uv >/dev/null || [ "$(uv --version | cut -d' ' -f2)" != "$UV_VERSION" ]; then
  curl -LsSf "https://astral.sh/uv/$UV_VERSION/install.sh" | env UV_NO_MODIFY_PATH=1 sh >/dev/null
fi
uv python install 3.13 >/dev/null

echo "== AVD envoy-test"
# Only when missing: a re-run must not wipe an AVD that is past its first boot (a new one needs a warm-up; docs/cloud.md).
[ -f "$HOME/.android/avd/envoy-test.avd/config.ini" ] || avdmanager create avd -n envoy-test -k "$IMAGE" -d pixel_6 </dev/null >/dev/null
python3 - "$HOME/.android/avd/envoy-test.avd/config.ini" "$HERE/envoy-test.config.ini" <<'EOF'
import sys
path, profile = sys.argv[1], sys.argv[2]
def read(p):
    return dict(line.rstrip("\n").split("=", 1) for line in open(p) if "=" in line)
cfg = read(path)
cfg.update(read(profile))  # the Mac's hardware lines win
cfg.update({"abi.type": "x86_64", "hw.cpu.arch": "x86_64",  # ...except the CPU: the Mac's image is arm64
            "image.sysdir.1": "system-images/android-35/google_apis_playstore/x86_64/"})
open(path, "w").write("".join(f"{k}={v}\n" for k, v in sorted(cfg.items())))
EOF

echo "== idle stop"
sudo tee /usr/local/bin/envoy-idle-stop >/dev/null <<'EOF'
#!/usr/bin/env bash
# Power off after 3 idle checks in a row (~45 min). Busy: an SSH session, an Envoy run (eval/ or a script), a client
# connected to the API on :8700 (the web app, the iPhone, Muse), or /etc/envoy-keep-awake (a demo day:
# scripts/cloud/keep-awake.sh on). A stopped VM costs only its disk.
STATE=/run/envoy-idle
if [ -e /etc/envoy-keep-awake ] || pgrep -f 'sshd(-session)?: [a-z_][a-z0-9_-]*@' >/dev/null ||
   pgrep -f 'eval/|scripts/(run_task|compile_routine|measure_device)' >/dev/null ||
   [ -n "$(ss -Htn state established '( sport = :8700 )' 2>/dev/null)" ]; then
  echo 0 >"$STATE"; exit 0
fi
n=$(( $(cat "$STATE" 2>/dev/null || echo 0) + 1 )); echo "$n" >"$STATE"
[ "$n" -ge 3 ] && { logger "envoy-idle-stop: idle 45 min, powering off"; systemctl poweroff; }
EOF
sudo chmod 755 /usr/local/bin/envoy-idle-stop
sudo tee /etc/systemd/system/envoy-idle-stop.service >/dev/null <<'EOF'
[Unit]
Description=Envoy: power off when idle
[Service]
Type=oneshot
ExecStart=/usr/local/bin/envoy-idle-stop
EOF
sudo tee /etc/systemd/system/envoy-idle-stop.timer >/dev/null <<'EOF'
[Unit]
Description=Envoy: check for idle every 15 minutes
[Timer]
OnBootSec=15min
OnUnitActiveSec=15min
[Install]
WantedBy=timers.target
EOF
sudo systemctl daemon-reload && sudo systemctl enable --now envoy-idle-stop.timer >/dev/null 2>&1

echo "== versions"
{
  echo "kernel: $(uname -r)"; echo "cpu: $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2- | xargs) x $(nproc)"
  echo "java: $(java -version 2>&1 | head -1)"
  for p in cmdline-tools/latest platform-tools emulator "system-images/android-35/google_apis_playstore/x86_64"; do
    echo "$p: $(grep -h Pkg.Revision "$SDK/$p/source.properties" | cut -d= -f2)"
  done
  echo "uv: $(uv --version)"; echo "python: $(uv python find 3.13)"
  echo "accel: $(sg kvm -c 'emulator -accel-check' 2>&1 | tr '\n' ' ')"
} | tee "$HOME/cloud-versions.txt"
