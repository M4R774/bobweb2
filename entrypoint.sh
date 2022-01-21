#!/bin/bash
cd web || exit
python3 manage.py migrate
cd ../bob || exit
python3 main.py
