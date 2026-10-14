#!/bin/bash
{
  echo
  echo
  echo "[$(date)]: Starting deployment"

  # Create new sqlite file if it does not exist
  touch web/db.sqlite3
  # Container runs as non-root user (uid 1000) so the bind mounted file must be writable by any user
  chmod a+rw web/db.sqlite3

  # Use .env file for docker compose environment interpolation and container env vars if present
  if [ -f .env ]; then
    docker compose --env-file .env -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans
  else
    docker compose -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans
  fi

  echo "[$(date)]: Deployment finished"
} 2>&1 | tee docker-compose.dev.log
