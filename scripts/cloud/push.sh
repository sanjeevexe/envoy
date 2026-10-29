#!/usr/bin/env bash
# Send Envoy's code to the VM (run on the Mac): tracked files only, from a commit, plus SkyLark's debug APK.
#
#   scripts/cloud/push.sh            # main's current commit
#   scripts/cloud/push.sh <commit>
#
# `git archive` holds tracked files only, so no .env, data/api, logs or demo memory travels. The APK is build output
# (not tracked), so it is copied on its own to the same path, where backend/testapps/skylark.py installs it from.
# On the VM the code lands in ~/envoy, with the commit in ~/envoy/.cloud-commit and the APK's sha256 in
# ~/envoy/.cloud-apk-sha256. An older ~/envoy from another commit is kept as ~/envoy.<old short commit>.
source "$(dirname "$0")/config.sh"

COMMIT="$(git -C "$REPO" rev-parse "${1:-main}^{commit}")"
SHORT="${COMMIT:0:7}"
APK_REL="testapps/skylark/app/build/outputs/apk/debug/app-debug.apk"
APK="${ENVOY_SKYLARK_APK:-$HOME/Desktop/Envoy/$APK_REL}"
[ -f "$APK" ] || { echo "no SkyLark APK at $APK (build it, or set ENVOY_SKYLARK_APK)" >&2; exit 1; }
APK_SHA="$(shasum -a 256 "$APK" | cut -d' ' -f1)"

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
git -C "$REPO" archive --format=tar.gz -o "$stage/envoy-$SHORT.tar.gz" "$COMMIT"
cp "$APK" "$stage/app-debug.apk"
echo "commit $COMMIT, archive $(du -h "$stage/envoy-$SHORT.tar.gz" | cut -f1), APK sha256 $APK_SHA"

[ "$(vm_status)" = "RUNNING" ] || { echo "$VM is not running (scripts/cloud/start.sh --vm-only)" >&2; exit 1; }
vm_scp "$stage/envoy-$SHORT.tar.gz" "$stage/app-debug.apk" "$VM:~/"
vm_ssh --command "set -euo pipefail
  if [ -d ~/$REMOTE_DIR ] && [ \"\$(cat ~/$REMOTE_DIR/.cloud-commit 2>/dev/null)\" != '$COMMIT' ]; then
    old=\$(cut -c1-7 ~/$REMOTE_DIR/.cloud-commit 2>/dev/null || echo old); rm -rf ~/$REMOTE_DIR.\$old; mv ~/$REMOTE_DIR ~/$REMOTE_DIR.\$old
  fi
  mkdir -p ~/$REMOTE_DIR && tar -xzf ~/envoy-$SHORT.tar.gz -C ~/$REMOTE_DIR && rm ~/envoy-$SHORT.tar.gz
  echo $COMMIT > ~/$REMOTE_DIR/.cloud-commit
  mkdir -p ~/$REMOTE_DIR/\$(dirname $APK_REL) && mv ~/app-debug.apk ~/$REMOTE_DIR/$APK_REL
  echo \"$APK_SHA  $APK_REL\" > ~/$REMOTE_DIR/.cloud-apk-sha256
  cd ~/$REMOTE_DIR && sha256sum -c .cloud-apk-sha256
  source ~/env-linux.sh && uv sync --project backend --locked -q && echo 'uv sync done'"
echo "next: scripts/cloud/start.sh"
