#!/bin/bash
echo "Starting deployment"
BROADCAST_MESSAGE=$(git log -1 --pretty=%B)
export BROADCAST_MESSAGE
docker-compose up --build --detach --force-recreate --remove-orphans
