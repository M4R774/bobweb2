FROM python:3.10-slim-buster

WORKDIR /

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install --no-install-recommends git=1:2.20.1-2+deb10u3 \
    zlib1g-dev libjpeg-dev libpng-dev -y \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

COPY . .
CMD ["/bin/bash", "-c", "/entrypoint.sh"]