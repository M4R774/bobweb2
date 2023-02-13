#!/bin/bash

echo "Taking back ups from the db"
mkdir -p ../backups
touch bobweb/web/db.sqlite3
cp bobweb/web/db.sqlite3 "../backups/$(date +%F_%R).sqlite3"

echo "Starting deployment"
COMMIT_MESSAGE=$(git log -1 --pretty=%B)
COMMIT_AUTHOR_NAME=$(git log -1 --pretty=%an)
COMMIT_AUTHOR_EMAIL=$(git log -1 --pretty=%ae)
export COMMIT_MESSAGE
export COMMIT_AUTHOR_NAME
export COMMIT_AUTHOR_EMAIL

CPU_architecture=$'uname -m'
if [[ $CPU_architecture == 'arm7v' ]]; then
  docker-compose up --build --detach --force-recreate --remove-orphans
else
  docker-compose up -f ci.docker-compose.yml --build --detach --force-recreate --remove-orphans
fi
