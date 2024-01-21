#!/bin/bash

# Define the Docker image name and version
IMAGE_NAME="latemus/bobweb2:main"

# Function to check if a new version is available
function is_new_version_available() {
    LATEST_VERSION=$(docker pull $IMAGE_NAME | grep -c "Status: Downloaded newer image")
    if [ "$LATEST_VERSION" -gt 0 ]; then
        return 0 # New version available
    else
        return 1 # No new version available
    fi
}

# Check if a new version is available
if is_new_version_available; then
    echo "New version of $IMAGE_NAME is available. Deploying."
    docker-compose -f docker-compose.prod.dockerhub.yml up --build --detach --force-recreate --remove-orphans |& tee docker-compose.dockerhub.log
else
    echo "No new version available. No action taken."
fi
