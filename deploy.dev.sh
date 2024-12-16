#!/bin/bash
echo -e "\n\n\n[$(date)]: Starting deployment"
touch bobweb/web/db.sqlite3
docker compose -f docker-compose.dev.yml up --build --force-recreate --remove-orphans
echo -e "[$(date)]: Deployment finished"
