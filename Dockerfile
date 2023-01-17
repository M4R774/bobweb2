FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -y && apt-get -y install --no-install-recommends \
    gdal-bin=3.2.2+dfsg-2+deb11u2 \
    libgdal-dev=3.2.2+dfsg-2+deb11u2 \
    proj-bin=7.2.1-1 \
    firefox-esr=91.13.0esr-1~deb11u1 \
    && rm -rf /var/lib/apt/lists/*

ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

RUN pip3 install --no-cache-dir setuptools==57.5.0
RUN pip3 install --no-cache-dir gdal==3.2.2

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]