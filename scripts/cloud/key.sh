#!/usr/bin/env bash
# Put the Meta API key on the VM for a model-calling stage, and take it off again (run on the Mac). Only with the
# user's yes for that stage.
#
#   scripts/cloud/key.sh put [cap_usd]   # ~/envoy/.env on the VM (mode 600): the key, and a daily cap (default $1)
#   scripts/cloud/key.sh remove          # delete it, then check no file in ~/envoy, the shell history or /tmp holds the key
#
# The key goes from the Mac's .env to the VM through the SSH session's stdin: never on a command line, in a
# transcript or in a log. META_DAILY_COST_CAP_USD is Envoy's own guard (models/adapter.py, CostMeter); on the VM it
# counts only the VM's spend (its own logs/model_costs.jsonl), so the cap is the stage's whole budget.
source "$(dirname "$0")/config.sh"
ENV_FILE="${ENVOY_ENV_FILE:-$HOME/Desktop/Envoy/.env}"
key_line() { grep -E '^META_API_KEY=.+' "$ENV_FILE" || { echo "no META_API_KEY in $ENV_FILE" >&2; exit 1; }; }

case "${1:-}" in
  put)
    cap="${2:-1}"
    { key_line; grep -E '^META_API_BASE_URL=' "$ENV_FILE" || true; echo "META_DAILY_COST_CAP_USD=$cap"; } |
      vm_ssh_once --command "umask 077 && cat > ~/$REMOTE_DIR/.env && chmod 600 ~/$REMOTE_DIR/.env && echo \"key on the VM (cap \$$cap), \$(stat -c %a ~/$REMOTE_DIR/.env)\""
    ;;
  remove)
    key_line | sed 's/^META_API_KEY=//' |
      vm_ssh_once --command "rm -f ~/$REMOTE_DIR/.env
        hits=\$(grep -rlF -f /dev/stdin ~/$REMOTE_DIR ~/.bash_history /tmp --exclude-dir=.venv 2>/dev/null | wc -l)
        [ \"\$hits\" = 0 ] && echo 'key removed; no file on the VM holds it' || { echo \"key still in \$hits file(s)\" >&2; exit 1; }"
    ;;
  *) echo "usage: $0 put [cap_usd] | remove" >&2; exit 2 ;;
esac
