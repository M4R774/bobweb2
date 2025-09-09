#!/bin/bash
{
  echo "[$(date)]: Building image"
  docker build --progress=plain --tag bobweb-test-container .
  echo
  echo
  echo "[$(date)]: Running test container"
  docker run --rm -a stdout -a stderr bobweb-test-container python -u web/manage.py test bobweb
  echo "[$(date)]: Test run finished"
} 2>&1 | tee docker-test-run.log 2>&1
