#!/bin/bash

PYTHONPATH=$(pwd)
export PYTHONPATH

python bobweb/web/manage.py migrate --no-input
python bobweb/web/manage.py collectstatic --noinput  # Builds static files for web build
python bobweb/bob/main.py
