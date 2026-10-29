# Shared settings for scripts/cloud/*.sh (run on the Mac). Sourced, not run.
#
# Everything can be overridden from the environment, e.g. ENVOY_GCP_ZONE=us-east4-a scripts/cloud/create.sh
# The project is the one `gcloud config set project <id>` chose, unless ENVOY_GCP_PROJECT is set.
set -euo pipefail

PROJECT="${ENVOY_GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
[ -n "$PROJECT" ] || { echo "no project: run gcloud config set project <id> (or set ENVOY_GCP_PROJECT)" >&2; exit 2; }
REGION="${ENVOY_GCP_REGION:-us-east1}"
ZONE="${ENVOY_GCP_ZONE:-$REGION-b}"
VM="${ENVOY_GCP_VM:-envoy-cloud}"
MACHINE="${ENVOY_GCP_MACHINE:-n2-standard-8}"  # 8 vCPU, 32 GB; about $0.39/h on demand in us-east1 (Oct 2026)
DISK_GB="${ENVOY_GCP_DISK_GB:-50}"              # balanced PD, about $0.10/GB-month; it can grow later, never shrink
NETWORK="${ENVOY_GCP_NETWORK:-envoy-cloud}"     # our own VPC: its only ingress rule is SSH from Google's IAP range
SUBNET_RANGE="${ENVOY_GCP_SUBNET_RANGE:-10.80.0.0/24}"
LABELS="envoy=cloud-proof"
REMOTE_DIR="envoy"                               # the code's folder in the VM user's home

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GC=(gcloud --project "$PROJECT" --quiet)

# SSH and scp only through IAP: the VM accepts no other inbound connection.
vm_ssh() { "${GC[@]}" compute ssh "$VM" --zone "$ZONE" --tunnel-through-iap "$@"; }
vm_scp() { "${GC[@]}" compute scp --zone "$ZONE" --tunnel-through-iap "$@"; }
vm_status() { "${GC[@]}" compute instances describe "$VM" --zone "$ZONE" --format='value(status)' 2>/dev/null || true; }
