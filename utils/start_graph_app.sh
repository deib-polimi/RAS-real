#! /bin/bash
# Launch graph_set + graph_quota containers with PATCHED web_server_graph_mst.py
# mounted on top of the image's broken hardcoded version.
#
# Why the mount: the image's built-in /usr/src/app/web_server_graph_mst.py
# ignores request bodies and always uses {'size':25000}, killing any noise we
# inject client-side. We override it with web_server_graph_mst_fixed.py which
# reads `request.get_json()` properly.

set -euo pipefail
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
FIXED="$SCRIPT_DIR/web_server_graph_mst_fixed.py"

if [ ! -f "$FIXED" ]; then
    echo "ERROR: $FIXED not found" >&2
    exit 1
fi

# Clean up any previous instances (idempotent).
docker rm -f graph_set graph_quota 2>/dev/null || true

docker run --name graph_set -d -p 8080:8080 \
    -v "$FIXED:/usr/src/app/web_server_graph_mst.py:ro" \
    systemautoscaler/sebs-dynamic_html:0.0.1 \
    uwsgi --http 0.0.0.0:8080 --master -p 15 -w web_server_graph_mst:app

docker run --name graph_quota -d -p 8081:8080 \
    -v "$FIXED:/usr/src/app/web_server_graph_mst.py:ro" \
    systemautoscaler/sebs-dynamic_html:0.0.1 \
    uwsgi --http 0.0.0.0:8080 --master -p 1 -w web_server_graph_mst:app

echo "Containers started. Verifying patch is mounted..."
sleep 2
docker exec graph_set grep -q 'request.get_json' /usr/src/app/web_server_graph_mst.py \
    && echo "  graph_set: patch present ✓" \
    || echo "  graph_set: PATCH MISSING ✗"
docker exec graph_quota grep -q 'request.get_json' /usr/src/app/web_server_graph_mst.py \
    && echo "  graph_quota: patch present ✓" \
    || echo "  graph_quota: PATCH MISSING ✗"
