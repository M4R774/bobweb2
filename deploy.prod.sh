#!/bin/bash

echo "Taking back ups from the db"
mkdir -p ../backups
touch web/db.sqlite3
cp web/db.sqlite3 "../backups/$(date +%F_%R).sqlite3"

COMMIT_MESSAGE=$(git log -1 --pretty=%B)
COMMIT_AUTHOR_NAME=$(git log -1 --pretty=%an)
COMMIT_AUTHOR_EMAIL=$(git log -1 --pretty=%ae)
export COMMIT_MESSAGE
export COMMIT_AUTHOR_NAME
export COMMIT_AUTHOR_EMAIL

{
  echo "[$(date)]: Starting deployment"
  CPU_architecture=$(uname -m)
  if [[ $CPU_architecture == 'armv7l' ]]; then
    docker compose -f docker-compose.prod.yml up --build --detach --force-recreate --remove-orphans
  else
    docker compose -f docker-compose.ci.yml up --build --detach --force-recreate --remove-orphans
  fi
echo "[$(date)]: Deployment done"
} 2>&1 | tee docker-compose.prod.log
