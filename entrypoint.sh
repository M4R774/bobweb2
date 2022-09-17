#!/bin/bash
export PYTHONPATH=$(pwd)
python bobweb/web/manage.py migrate --no-input
python bobweb/bob/main.py
