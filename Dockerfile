FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -y && apt-get -y install --no-install-recommends \
    libgeos-dev=3.9.0-1 \
    chromium-common=108.0.5359.94-1~deb11u1

RUN apt-get -y install --no-install-recommends \
    chromium=108.0.5359.94-1~deb11u1

RUN apt-get -y install --no-install-recommends \
    chromium-driver=108.0.5359.94-1~deb11u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]