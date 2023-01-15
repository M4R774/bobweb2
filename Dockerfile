FROM python:3.10-slim-buster

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -y && apt-get -y install --no-install-recommends \
    gcc=4:8.3.0-1 \
    libjpeg-dev=1:1.5.2-2+deb10u1 \
    zlib1g=1:1.2.11.dfsg-1+deb10u2 \
    zlib1g-dev=1:1.2.11.dfsg-1+deb10u2 \
    firefox=108.0.2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]