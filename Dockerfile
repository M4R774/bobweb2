FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -y && apt-get -y install --no-install-recommends \
    firefox-esr=91.13.0esr-1~deb11u1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --extra-index-url https://www.piwheels.org/simple --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]