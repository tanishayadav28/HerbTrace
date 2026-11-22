#!/usr/bin/env bash
# Render build script: install, collect static files, migrate, seed demo data once.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --no-input
python manage.py migrate --no-input
if [ "$SEED_DEMO" = "1" ]; then
  python manage.py seed_demo --force
fi