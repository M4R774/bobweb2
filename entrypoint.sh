#!/bin/bash

PYTHONPATH=$(pwd)
export PYTHONPATH

# Replace \n with actual newlines and export as an environment variable
COMMIT_MESSAGE=$(echo -e "${COMMIT_MESSAGE}")
export COMMIT_MESSAGE

python bobweb/web/manage.py migrate --no-input
python bobweb/web/manage.py collectstatic --noinput  # Builds static files for web build
python bobweb/bob/main.py
