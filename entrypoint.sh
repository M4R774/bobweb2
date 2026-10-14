#!/bin/bash

PYTHONPATH=$(pwd)
export PYTHONPATH

# Replace sed escaped linebreaks '\n' with actual non-escaped newlines and export as an environment variable
COMMIT_MESSAGE=$(echo -e "${COMMIT_MESSAGE}")
export COMMIT_MESSAGE

python web/manage.py migrate --no-input
python web/manage.py collectstatic --noinput  # Builds static files for web build
# exec replaces the shell so that python is PID 1 and receives SIGTERM from docker stop
exec python bot/main.py
