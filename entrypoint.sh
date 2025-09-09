#!/bin/bash

PYTHONPATH=$(pwd)
export PYTHONPATH

# Replace sed escaped linebreaks '\n' with actual non-escaped newlines and export as an environment variable
COMMIT_MESSAGE=$(echo -e "${COMMIT_MESSAGE}")
export COMMIT_MESSAGE

python web/manage.py migrate --no-input
python web/manage.py collectstatic --noinput  # Builds static files for web build
python bot/main.py
