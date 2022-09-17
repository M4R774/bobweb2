#!/bin/bash
python3 bobweb/web/manage.py migrate --no-input
python3 bobweb/bob/main.py
