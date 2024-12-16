#!/bin/bash

# Note! As this file might be referenced from a cron job running on bots production environment, any path or name
# changes are breaking and require manual change to the cron job on the running environment.
# If deployments are done with images built in github actions and stored in dockerhub, this is the only file from the
# project repository needed on the server host machine.

# script for checking latest version of docker image from dockerhub and then
# deploying it if there is newer image available. Can be ran for example as a cron job.
# To edit cron jobs on linux based system run command `crontab -e` and then add new cron job row.
#
# Example of cron-job configuration for running script at every 5 minutes:
# */5 * * * *  cd /{path-to-the-root-of-the-project} && ./deploy.prod.from_dockerhub.sh  >> deploy.prod.from_dockerhub.log
# Explanation: every 5 minutes run following command. 1. CD to defined path, 2. run this script while
# logging this script run to a log file

# Define the Docker image name and tag. Only main-tagged images are checked
IMAGE_NAME="latemus/bobweb2:main"
LOG_FILE_PATH="docker-compose.prod.dockerhub.log"

# Function to check if a new version is available
function is_new_version_available() {
    LATEST_VERSION=$(docker pull $IMAGE_NAME | grep -c "Status: Downloaded newer image")
    if [ "$LATEST_VERSION" -gt 0 ]; then
        return 0 # New version available
    else
        return 1 # No new version available
    fi
}


{
  # Check if a new version is available
  if is_new_version_available;
    then
        # If so, do same deployment as in deploy.prod.sh
        # however this uses different different docker compose configuration
        echo -e "[$(date)]: New version of $IMAGE_NAME is available. Deploying."
        echo "Taking back ups from the db"
        # create new backups and 'bobweb/web' folders if the do ynot exists
        mkdir -p bobweb/web
        touch bobweb/web/db.sqlite3
        mkdir -p ../backups
        cp bobweb/web/db.sqlite3 "../backups/$(date +%F_%R).sqlite3"

        COMMIT_MESSAGE=$(git log -1 --pretty=%B)
        COMMIT_AUTHOR_NAME=$(git log -1 --pretty=%an)
        COMMIT_AUTHOR_EMAIL=$(git log -1 --pretty=%ae)
        export COMMIT_MESSAGE
        export COMMIT_AUTHOR_NAME
        export COMMIT_AUTHOR_EMAIL

        # Note! Without `--build`-flag as the image is fetched from dockerhub
        # Note! uses 'docker compose', not 'docker-compose' -command
        docker compose -f docker-compose.prod.dockerhub.yml up --detach --force-recreate --remove-orphans
        echo -e "[$(date)]: Deployment done"
    else
        echo -e "[$(date)]: No new version available. No action taken."
  fi
} |& tee $LOG_FILE_PATH
