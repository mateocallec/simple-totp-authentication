#!/bin/bash
set -e

echo "[INFO] Container starting..."

exec python3 -m gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 4 \
    --access-logfile - \
    --error-logfile - \
    app:app
