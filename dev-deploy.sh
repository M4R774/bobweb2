#!/bin/bash
{
  echo -e "\n\n\n[$(date)]: Starting deployment"
  docker-compose -f dev.docker-compose.yml up --build --detach --force-recreate --remove-orphans
  echo -e "[$(date)]: Deployment finished"
} &>> dev-docker-compose.log
