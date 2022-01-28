#!/bin/bash
echo "Starting deployment"
COMMIT_MESSAGE=$(git log -1 --pretty=%B)
COMMIT_AUTHOR_NAME=$(git log -1 --pretty=%an)
COMMIT_AUTHOR_EMAIL=$(git log -1 --pretty=%ae)
export COMMIT_MESSAGE
export COMMIT_AUTHOR_NAME
export COMMIT_AUTHOR_EMAIL
docker-compose up --build --detach --force-recreate --remove-orphans
