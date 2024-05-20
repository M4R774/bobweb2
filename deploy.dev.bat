echo "Starting deployment"
docker compose -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans > docker-compose.dev.log
