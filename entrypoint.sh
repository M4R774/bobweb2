#!/bin/bash

PYTHONPATH=$(pwd)
export PYTHONPATH

python bobweb/web/manage.py migrate --no-input
python bobweb/bob/main.py
