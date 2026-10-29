#!/usr/bin/env bash
# Create Envoy's cloud VM from a clean Google Cloud project (run on the Mac, after gcloud auth login).
#
#   scripts/cloud/create.sh          # check the project's limits, then create the network and the VM
#   scripts/cloud/create.sh --check  # only print the limits (CPU quotas), create nothing
#
# What it makes, all labelled envoy=cloud-proof where GCE allows labels:
#   - network envoy-cloud (custom mode) with one subnet in $REGION
#   - firewall envoy-cloud-iap-ssh: tcp:22 from 35.235.240.0/20 only (Google's IAP forwarders). There is no other
#     ingress rule, so nothing on the internet can reach the VM; SSH goes through `gcloud compute ssh --tunnel-through-iap`
#   - VM envoy-cloud: Ubuntu 24.04, n2-standard-8, nested virtualization (KVM for the emulator), no service account
#     (nothing on the VM can call Google APIs), an ephemeral external IPv4 for outbound downloads only
# Costs start when the VM runs; scripts/cloud/stop.sh stops it. Deleting is scripts/cloud/delete.sh (the user's call).
source "$(dirname "$0")/config.sh"

echo "project $PROJECT, zone $ZONE, $MACHINE, ${DISK_GB} GB"
"${GC[@]}" services enable compute.googleapis.com iap.googleapis.com

quota() {  # quota <json from describe> <metric>: "usage/limit"
  python3 -c 'import json,sys; q={x["metric"]: x for x in json.load(sys.stdin)["quotas"]}; m=q.get(sys.argv[1]); print("%g/%g" % (m["usage"], m["limit"]) if m else "none")' "$2" <<<"$1"
}
REG_JSON="$("${GC[@]}" compute regions describe "$REGION" --format=json)"
PRJ_JSON="$("${GC[@]}" compute project-info describe --format=json)"
echo "quotas (used/limit): CPUS_ALL_REGIONS $(quota "$PRJ_JSON" CPUS_ALL_REGIONS), $REGION CPUS $(quota "$REG_JSON" CPUS)," \
     "N2_CPUS $(quota "$REG_JSON" N2_CPUS), SSD_TOTAL_GB $(quota "$REG_JSON" SSD_TOTAL_GB), IN_USE_ADDRESSES $(quota "$REG_JSON" IN_USE_ADDRESSES)"
[ "${1:-}" = "--check" ] && exit 0

if ! "${GC[@]}" compute networks describe "$NETWORK" >/dev/null 2>&1; then
  "${GC[@]}" compute networks create "$NETWORK" --subnet-mode=custom
  "${GC[@]}" compute networks subnets create "$NETWORK-$REGION" --network "$NETWORK" --region "$REGION" --range "$SUBNET_RANGE"
fi
if ! "${GC[@]}" compute firewall-rules describe "$NETWORK-iap-ssh" >/dev/null 2>&1; then
  "${GC[@]}" compute firewall-rules create "$NETWORK-iap-ssh" --network "$NETWORK" --direction INGRESS \
    --allow tcp:22 --source-ranges 35.235.240.0/20 --description "Envoy cloud-proof: SSH through IAP only"
fi

if [ -n "$(vm_status)" ]; then echo "$VM already exists ($(vm_status))"; exit 0; fi
"${GC[@]}" compute instances create "$VM" --zone "$ZONE" --machine-type "$MACHINE" \
  --enable-nested-virtualization \
  --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud \
  --boot-disk-size "${DISK_GB}GB" --boot-disk-type pd-balanced \
  --subnet "$NETWORK-$REGION" \
  --no-service-account --no-scopes \
  --labels "$LABELS"
echo "created $VM; next: scripts/cloud/setup.sh"
