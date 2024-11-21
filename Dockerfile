FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -qqy \
    && apt-get -y install --no-install-recommends \
    libgeos-dev=3.9.0-1 ffmpeg=7:4.3.6-0+deb11u1 libavcodec-extra=7:4.3.6-0+deb11u1 \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

COPY requirements.txt requirements.txt

RUN if [ "$(uname -m)" = armv7l ]; then \
    # Install python packages. --force-pi is needed for Adafruit-DHT when installing on
    # any other armv7l platform other than Raspberry Pi, for example when building multi-arch docker image.
    pip3 install --no-cache-dir Adafruit-DHT==1.4.0 --install-option '--force-pi'; \
    fi \
    && pip3 install --no-cache-dir -r requirements.txt
# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
