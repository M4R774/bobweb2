#!/bin/bash
{
  echo -e "\n\n\n[$(date)]: Starting deployment"
  # create new sqlite file folder if it does not exists
  touch bobweb/web/db.sqlite3
  docker compose -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans
  echo -e "[$(date)]: Deployment finished"
} |& tee docker-compose.dev.log