FROM python:3.10-buster

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -y && apt-get -y install --no-install-recommends \
    gdal-bin=2.4.0+dfsg-1+deb10u1 \
    proj-bin=5.2.0-1 \
    firefox-esr=102.6.0esr-1~deb10u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]