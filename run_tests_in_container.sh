#!/bin/bash
{
  echo -e "[$(date)]: Building image"
  docker build --progress=plain --tag bobweb-test-container .
  echo -e "\n\n\n[$(date)]: Running test container"
  docker run --rm -a stdout -a stderr bobweb-test-container python -u bobweb/web/manage.py test bobweb
  echo -e "[$(date)]: Test run finished"
} > docker-test-run.log 2>&1