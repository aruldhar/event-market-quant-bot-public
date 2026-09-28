#!/usr/bin/env sh
# Archive one fully closed Candidate-E run, then optionally prune its local
# run-scoped evidence.  This is intended to be invoked after the shadow
# closeout sidecar has written its receipt; it never removes evidence unless
# --confirm-prune is passed and the archive command has completed successfully.
set -eu

usage() {
  cat <<'EOF'
Usage: finalize-kxbtcd-terminal-run.sh --run-id ID --bucket NAME [options]

Required:
  --run-id ID                 Completed Candidate-E run identifier
  --bucket NAME               Private evidence S3 bucket

Options:
  --prefix PREFIX             S3 prefix (default: candidate-e)
  --region REGION             AWS region (default: us-east-1)
  --confirm-prune             Verify the archive again, then delete only this
                              run's local raw, telemetry, and live-shadow files.
                              The shared shadow ledger is always retained.

Run without --confirm-prune immediately after closeout.  Schedule or rerun it
with --confirm-prune only after the chosen local retention window.
EOF
}

run_id=
bucket=
prefix=candidate-e
region=us-east-1
confirm_prune=false

while [ "$#" -gt 0 ]; do
  case "$1" in
    --run-id) run_id=${2:?missing run id}; shift 2 ;;
    --bucket) bucket=${2:?missing bucket}; shift 2 ;;
    --prefix) prefix=${2:?missing prefix}; shift 2 ;;
    --region) region=${2:?missing region}; shift 2 ;;
    --confirm-prune) confirm_prune=true; shift ;;
    --help|-h) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

[ -n "$run_id" ] && [ -n "$bucket" ] || { usage >&2; exit 2; }
case "$run_id" in *[!A-Za-z0-9_-]*|'') echo "invalid --run-id" >&2; exit 2 ;; esac

compose_file=deploy/kxbtcd-candidate-e-soak.compose.yaml
receipt=/var/lib/kxbtcd-offsite-archive-receipts/${run_id}.json
closeout=/var/lib/kxbtcd-soak/live-shadow/${run_id}/settlement_closeout.json

# A terminal soak manifest alone is not enough: the live-shadow settlement
# sidecar must also have sealed its own result before its files are archived.
sudo docker run --rm \
  -v deploy_soak_raw:/var/lib/kxbtcd-soak:ro \
  busybox:1.36 test -f "$closeout"

sudo docker compose -f "$compose_file" up --force-recreate \
  soak_volume_init shadow_dashboard_volume_init offsite_archive_receipts_volume_init

sudo docker compose -f "$compose_file" run --rm --no-deps \
  candidate_e_offsite_archive \
  --run-id "$run_id" \
  --bucket "$bucket" \
  --prefix "$prefix" \
  --region "$region" \
  --raw-root /var/lib/kxbtcd-soak/raw \
  --telemetry-root /var/lib/kxbtcd-soak/telemetry \
  --live-shadow-root /var/lib/kxbtcd-soak/live-shadow \
  --shadow-ledger /var/lib/kxbtcd-shadow-dashboard/live_shadow_simulation.sqlite3 \
  --receipt "$receipt"

if [ "$confirm_prune" = true ]; then
  sudo docker compose -f "$compose_file" run --rm --no-deps \
    candidate_e_verified_local_prune \
    --receipt "$receipt" \
    --raw-root /var/lib/kxbtcd-soak/raw \
    --telemetry-root /var/lib/kxbtcd-soak/telemetry \
    --live-shadow-root /var/lib/kxbtcd-soak/live-shadow \
    --region "$region" \
    --confirm-prune
fi
