#!/bin/bash
{
  echo -e "[$(date)]: Staring test run"
  docker build --tag bobweb-test-container .
  docker run --rm -a stdout -it bobweb-test-container python bobweb/web/manage.py test bobweb \
  && echo -e "[$(date)]: Test run finished"
} &> docker-test-run.log
