echo "Starting deployment"

REM If .env exists, pass it to docker compose so it can populate variables inside containers
IF EXIST .env (
  SET DOCKER_ENV_ARG=--env-file .env
) ELSE (
  SET DOCKER_ENV_ARG=
)

docker compose %DOCKER_ENV_ARG% -f docker-compose.dev.yml up --build --detach --force-recreate --remove-orphans > docker-compose.dev.log
