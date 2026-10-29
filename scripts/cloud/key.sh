#!/usr/bin/env bash
# Put the Meta API key on the VM for a model-calling stage, and take it off again (run on the Mac). Only with the
# user's yes for that stage.
#
#   scripts/cloud/key.sh put [cap_usd]   # the key and a daily cap (default $1) into the VM's .env (mode 600)
#   scripts/cloud/key.sh remove          # delete the key's line, then check no file in ~/envoy, ~/envoy-state, the shell
#                                        # history or /tmp holds the key
#
# The key goes from the Mac's .env to the VM through the SSH session's stdin: never on a command line, in a
# transcript or in a log. META_DAILY_COST_CAP_USD is Envoy's own guard (models/adapter.py, CostMeter); on the VM it
# counts only the VM's spend (its own logs/model_costs.jsonl), so the cap is the stage's whole budget.
source "$(dirname "$0")/config.sh"
ENV_FILE="${ENVOY_ENV_FILE:-$HOME/Desktop/Envoy/.env}"
key_line() { grep -E '^META_API_KEY=.+' "$ENV_FILE" || { echo "no META_API_KEY in $ENV_FILE" >&2; exit 1; }; }

# The VM's .env may hold other settings (the cloud copy's, envoy-setup.sh): only the key and cap lines are touched.
ENV_VM="f=\$(readlink -f ~/$REMOTE_DIR/.env 2>/dev/null || echo ~/$REMOTE_DIR/.env)"

case "${1:-}" in
  put)
    cap="${2:-1}"
    { key_line; echo "META_DAILY_COST_CAP_USD=$cap"; } |
      vm_ssh_once --command "$ENV_VM; umask 077; touch \"\$f\"; sed -i '/^META_API_KEY=/d;/^META_DAILY_COST_CAP_USD=/d' \"\$f\"
        cat >> \"\$f\" && chmod 600 \"\$f\" && echo \"key on the VM (daily cap $cap USD), \$(stat -c %a \"\$f\")\""
    ;;
  remove)
    key_line | sed 's/^META_API_KEY=//' |
      vm_ssh_once --command "$ENV_VM; [ -f \"\$f\" ] && sed -i '/^META_API_KEY=/d' \"\$f\"
        hits=\$(grep -rlF -f /dev/stdin ~/$REMOTE_DIR ~/envoy-state ~/.bash_history /tmp --exclude-dir=.venv --exclude-dir=node_modules 2>/dev/null | wc -l)
        [ \"\$hits\" = 0 ] && echo 'key removed; no file on the VM holds it' || { echo \"key still in \$hits file(s)\" >&2; exit 1; }"
    ;;
  *) echo "usage: $0 put [cap_usd] | remove" >&2; exit 2 ;;
esac
