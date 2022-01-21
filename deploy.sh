echo "Starting deployment"
cd web || exit
python3 manage.py migrate
cd ..
docker build . -t bobweb
docker stop bobweb
docker rm bobweb
docker run --restart=always -d --name bobweb bobweb
