#!/bin/bash
{
  echo
  echo
  echo "[$(date)]: Starting deployment"

  # Create new sqlite file if it does not exist
  touch web/db.sqlite3

  docker compose -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans

  echo "[$(date)]: Deployment finished"
} 2>&1 | tee docker-compose.dev.log
