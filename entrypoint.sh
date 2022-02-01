#!/bin/bash
cd web || exit
python3 manage.py migrate --no-input
cd ../bob || exit
python3 main.py1
