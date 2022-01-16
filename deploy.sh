echo "Starting deployment"
docker build . -t bobweb
docker run bobweb