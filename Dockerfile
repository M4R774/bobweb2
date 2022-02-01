FROM python:3.10-slim-buster

WORKDIR .

RUN apt-get update && apt-get install git -y
COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
CMD ["/bin/bash", "-c", "/entrypoint.sh"]
