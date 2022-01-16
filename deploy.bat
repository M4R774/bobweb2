echo "Starting deployment"
docker build . -t bobweb
docker stop bobweb
docker rm bobweb
docker run -d --name bobweb bobweb