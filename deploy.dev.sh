#!/bin/bash
{
  echo -e "\n\n\n[$(date)]: Starting deployment"
  docker compose -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans
  echo -e "[$(date)]: Deployment finished"
} > docker-compose.dev.log 2>&1
