#!/bin/bash
python3 web/manage.py migrate --no-input
python3 bob/main.py
