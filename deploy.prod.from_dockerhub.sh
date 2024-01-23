#!/bin/bash

# script for checking latest version of docker image from dockerhub and then
# deploying it if there is newer image available. Can be ran for example as a cron job.
# To edit cron jobs on linux based system run command `crontab -e` and then add new cron job row.
#
# Example of cron-job configuration for running script at every 5 minutes:
# */5 * * * * /{path_to_this_script}/deploy_from_dockerhub.sh >> /{path_to_any_location_for_logs}/deploy_from_dockerhub.log

# Note! As this file might be referenced from a cron job running on bots production environment, any path or name
# changes are breaking and require manual change to the cron job.

# Define the Docker image name and tag. Only main-tagged images are checked
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
  # If so, do same deployment as in deploy.prod.sh
  # however this uses different different docker-compose configuration
  {
    echo -e "[$(date)]: New version of $IMAGE_NAME is available. Deploying."
    echo "Taking back ups from the db"
    mkdir -p ../backups
    touch bobweb/web/db.sqlite3
    cp bobweb/web/db.sqlite3 "../backups/$(date +%F_%R).sqlite3"

    COMMIT_MESSAGE=$(git log -1 --pretty=%B)
    COMMIT_AUTHOR_NAME=$(git log -1 --pretty=%an)
    COMMIT_AUTHOR_EMAIL=$(git log -1 --pretty=%ae)
    export COMMIT_MESSAGE
    export COMMIT_AUTHOR_NAME
    export COMMIT_AUTHOR_EMAIL

    docker-compose -f docker-compose.prod.dockerhub.yml up --detach --force-recreate --remove-orphans
    echo -e "[$(date)]: Deployment done"
  } |& tee docker-compose.dockerhub.log

else
    echo -e "[$(date)]: No new version available. No action taken." |& tee docker-compose.dockerhub.log
fi
