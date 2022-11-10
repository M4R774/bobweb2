#!/bin/bash
echo "Starting deployment"
docker-compose -f dev.docker-compose.yml up --build --detach --force-recreate --remove-orphans
