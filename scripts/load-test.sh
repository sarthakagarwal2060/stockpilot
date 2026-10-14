#!/usr/bin/env bash
# Generates CPU load on the backend so the HPA scales out.
# Usage: URL=http://<ingress-host> ./scripts/load-test.sh [duration-seconds] [concurrency]
#        (watch in another terminal: kubectl get hpa -n stockpilot -w)
set -euo pipefail

URL="${URL:-http://stockpilot.local}"
DURATION="${1:-180}"
CONCURRENCY="${2:-20}"

echo "Hitting ${URL}/api/products/stats and /api/products with ${CONCURRENCY} workers for ${DURATION}s"
end=$((SECONDS + DURATION))

worker() {
  while [ "$SECONDS" -lt "$end" ]; do
    curl -s -o /dev/null "${URL}/api/products/stats" || true
    curl -s -o /dev/null "${URL}/api/products?search=a" || true
  done
}

for _ in $(seq "$CONCURRENCY"); do worker & done
wait
echo "Load test finished."
