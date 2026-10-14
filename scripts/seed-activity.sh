#!/usr/bin/env bash
# Creates some stock movements so the dashboard and Grafana business panels have data.
# Usage: URL=http://localhost:3000 ./scripts/seed-activity.sh
set -euo pipefail
URL="${URL:-http://localhost:3000}"

ids=$(curl -fsS "${URL}/api/products" | python3 -c 'import json,sys; print(" ".join(str(p["id"]) for p in json.load(sys.stdin)))')
for id in $ids; do
  curl -fsS -o /dev/null -X POST "${URL}/api/products/${id}/adjust" -H 'Content-Type: application/json' \
    -d '{"change": 25, "reason": "RESTOCK", "note": "Seed PO"}'
  curl -fsS -o /dev/null -X POST "${URL}/api/products/${id}/adjust" -H 'Content-Type: application/json' \
    -d '{"change": -3, "reason": "SALE", "note": "Seed order"}' || true
done
echo "Seeded movements for: ${ids}"
