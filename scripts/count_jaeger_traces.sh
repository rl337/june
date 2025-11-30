#!/bin/bash
# Count total traces in Jaeger by querying all services
# Usage: count_jaeger_traces.sh [jaeger_url]

JAEGER_URL="${1:-${JAEGER_URL:-http://localhost:16686}}"
TOTAL=0

echo "Counting traces per service..."
echo "================================"

for service in $(curl -s "$JAEGER_URL/api/services" 2>/dev/null | jq -r '.data[]' 2>/dev/null); do
    # Query with a very large limit to get all traces for this service
    count=$(curl -s "$JAEGER_URL/api/traces?service=$service&limit=100000" 2>/dev/null | jq '.data | length' 2>/dev/null || echo "0")
    if [ "$count" -gt 0 ]; then
        echo "$service: $count traces"
        TOTAL=$((TOTAL + count))
    fi
done

echo "================================"
echo "Total traces across all services: $TOTAL"
echo ""
echo "Note: This queries the Jaeger API. For in-memory storage,"
echo "traces are lost on container restart."


