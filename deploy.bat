echo "Starting deployment"
docker build . -t bobweb
docker stop bobweb
docker rm bobweb
docker run --restart=always -d --name bobweb bobweb
