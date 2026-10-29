#!/usr/bin/env bash
# Runs ON the VM (scripts/cloud/envoy-setup.sh copies it there with its files): the cloud copy of Envoy, beside the Mac's.
#
# After scripts/cloud/setup.sh (toolchain, envoy-test) and push.sh (the code in ~/envoy), this adds:
#   - envoy-real: the Mac envoy-real's hardware (envoy-real.config.ini: 16 GB data, Play Store), x86_64 image
#   - Node 24 LTS (pinned, checksum-checked) and the web app built from the pushed commit (web/out)
#   - Tailscale (Tailscale's apt repository); signing the VM in is the user's step (scripts/cloud/tailnet.sh)
#   - cloudflared (Cloudflare's apt repository), for Muse; starting a public tunnel is the user's step (muse-tunnel.sh)
#   - ~/envoy-state (mode 700), what survives a new push: .env (the Mac's settings, a $3 daily cap, the cloud copy's own
#     MCP token; the Meta key only through key.sh), api/ (ENVOY_API_DIR: its own session token, VAPID keys, tasks),
#     demo/ (a copy of the Mac's demo memory and test inbox), linked into ~/envoy (.env, data/api, data/demo)
#   - systemd: envoy-emulators (envoy-test, envoy-real) and envoy-api (127.0.0.1:8700), started at boot. The API's log
#     goes to ~/envoy-state/api.log, not the journal: it holds the sign-in link.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CODE="$HOME/envoy"
STATE="$HOME/envoy-state"
IMAGE="system-images;android-35;google_apis_playstore;x86_64"
NODE="v24.22.0"
NODE_SHA256="cc2f601cee82d9a5a233302fe307abc600727035fd7d2c3a3571755989e95008"
source "$HOME/env-linux.sh"
[ -d "$CODE/backend" ] || { echo "no code in $CODE: run scripts/cloud/push.sh first" >&2; exit 1; }

echo "== envoy-real"
if [ ! -f "$HOME/.android/avd/envoy-real.avd/config.ini" ]; then
  avdmanager create avd -n envoy-real -k "$IMAGE" -d pixel_6 </dev/null >/dev/null
  python3 - "$HOME/.android/avd/envoy-real.avd/config.ini" "$HERE/envoy-real.config.ini" <<'EOF'
import sys
path, profile = sys.argv[1], sys.argv[2]
def read(p):
    return dict(line.rstrip("\n").split("=", 1) for line in open(p) if "=" in line)
cfg = read(path)
cfg.update(read(profile))
cfg.update({"abi.type": "x86_64", "hw.cpu.arch": "x86_64", "image.sysdir.1": "system-images/android-35/google_apis_playstore/x86_64/"})
open(path, "w").write("".join(f"{k}={v}\n" for k, v in sorted(cfg.items())))
EOF
fi

echo "== Node $NODE and the web app"
if [ "$(node --version 2>/dev/null)" != "$NODE" ]; then
  tmp="$(mktemp -d)"
  curl -fsSL -o "$tmp/node.tar.xz" "https://nodejs.org/dist/$NODE/node-$NODE-linux-x64.tar.xz"
  echo "$NODE_SHA256  $tmp/node.tar.xz" | sha256sum -c -
  rm -rf "$HOME/node" && mkdir -p "$HOME/node" && tar -xJf "$tmp/node.tar.xz" -C "$HOME/node" --strip-components=1
  rm -rf "$tmp"
fi
(cd "$CODE/web" && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null && echo "web/out built")

echo "== Tailscale"
if ! command -v tailscale >/dev/null; then
  curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
  curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq tailscale >/dev/null
fi
tailscale version | head -1

echo "== cloudflared (for Muse; starting a tunnel is the user's step: scripts/cloud/muse-tunnel.sh)"
if ! command -v cloudflared >/dev/null; then
  curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
  echo 'deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main' |
    sudo tee /etc/apt/sources.list.d/cloudflared.list >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get update -q >/dev/null
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -yq cloudflared >/dev/null
fi
cloudflared --version | head -1

echo "== state"
mkdir -p "$STATE/api" "$STATE/demo" && chmod 700 "$STATE"
if [ ! -f "$STATE/.env" ]; then
  (umask 077; cat >"$STATE/.env" <<EOF
META_API_BASE_URL=https://api.meta.ai/v1
META_CONTRIBUTOR_TIER=true
META_DAILY_COST_CAP_USD=3
ENVOY_TEST_AVD=envoy-test
ENVOY_TEST_GRPC_PORT=8554
ENVOY_REAL_AVD=envoy-real
ENVOY_REAL_GRPC_PORT=8556
MCP_PORT=8765
REST_PORT=8766
MCP_BEARER_TOKEN=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
EOF
  )
fi
if [ -f "$HERE/memory.db" ] && [ ! -f "$STATE/demo/memory.db" ]; then
  mv "$HERE/memory.db" "$STATE/demo/memory.db"
  [ -d "$HERE/inbox" ] && rm -rf "$STATE/demo/inbox" && mv "$HERE/inbox" "$STATE/demo/inbox"
fi
ln -sfn "$STATE/.env" "$CODE/.env"
mkdir -p "$CODE/data" && rm -rf "$CODE/data/demo" "$CODE/data/api"
ln -sfn "$STATE/demo" "$CODE/data/demo"
ln -sfn "$STATE/api" "$CODE/data/api"  # = ENVOY_API_DIR; scripts that use data/api (start_muse_test.sh) find the same files

echo "== services"
(umask 077; touch "$STATE/api.log"); chmod 600 "$STATE/api.log"  # systemd appends to it; it holds the sign-in link
U="$(id -un)"; UID_="$(id -u)"
sudo tee /etc/systemd/system/envoy-emulators.service >/dev/null <<EOF
[Unit]
Description=Envoy cloud copy: envoy-test and envoy-real
After=network-online.target user@$UID_.service
Wants=user@$UID_.service
[Service]
Type=oneshot
RemainAfterExit=yes
User=$U
WorkingDirectory=$CODE
Environment=XDG_RUNTIME_DIR=/run/user/$UID_
# Both phones render with ANGLE on SwiftShader (env-linux.sh's -gpu swangle): plain SwiftShader crashed the emulator
# under DoorDash and Amazon, and envoy-test died on it again later (Oct 29), though it was a little faster on SkyLark.
ExecStart=/bin/bash -c 'source ~/env-linux.sh && scripts/start_emulator.sh envoy-test && scripts/start_emulator.sh envoy-real'
ExecStop=/bin/bash -c 'source ~/env-linux.sh && scripts/stop_emulator.sh envoy-real; scripts/stop_emulator.sh envoy-test'
TimeoutStartSec=900
TimeoutStopSec=300
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/envoy-api.service >/dev/null <<EOF
[Unit]
Description=Envoy cloud copy: API, web app and MCP on 127.0.0.1:8700
After=envoy-emulators.service tailscaled.service
Wants=envoy-emulators.service
# Restarting the phones restarts the API: it keeps each emulator's per-launch gRPC token from when it connected, so
# after an emulator restart its calls fail (UNAUTHENTICATED) until the API restarts (seen Oct 29).
PartOf=envoy-emulators.service
[Service]
User=$U
WorkingDirectory=$CODE
Environment=XDG_RUNTIME_DIR=/run/user/$UID_
Environment=ENVOY_API_DIR=$STATE/api
Environment=ENVOY_PORT=8700
Environment=ENVOY_PROFILE=demo
Environment=TAILSCALE=/usr/bin/tailscale
Environment=ENVOY_ALLOWED_HOSTS=127.0.0.1:8745,localhost:8745
ExecStart=/bin/bash -c 'source ~/env-linux.sh && exec uv run --project backend python -m api --profile demo'
StandardOutput=append:$STATE/api.log
StandardError=append:$STATE/api.log
Restart=on-failure
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable envoy-emulators.service envoy-api.service >/dev/null 2>&1
echo "installed; start with: sudo systemctl start envoy-emulators envoy-api"
