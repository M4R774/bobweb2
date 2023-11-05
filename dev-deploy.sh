#!/bin/bash
echo "[" + date + "]: Starting deployment" >> docker-compose.log
docker-compose -f dev.docker-compose.yml up --build --detach --force-recreate --remove-orphans &>> docker-compose.log
