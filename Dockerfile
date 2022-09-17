FROM python:3.10-slim-buster AS compile-image

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update && apt-get install --no-install-recommends -y \
    python3.7-dev=3.7.3-2+deb10u3 \
    python3-pip=18.1-5 \
    python3-setuptools=40.8.0-1 \
    gcc=4:8.3.0-1 \
    zlib1g-dev=1:1.2.11.dfsg-1+deb10u2 \
    libjpeg-dev=1:1.5.2-2+deb10u1 \
    libpng-dev=1.6.36-6 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/* \
 && python -m venv /venv

ENV PATH="/venv/bin:$PATH"
COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# Second stage for code and dependencies
FROM python:3.10-slim-buster AS build-image
WORKDIR /

# Pillow wants to use libjpeg binaries outside of venv
RUN apt-get update && apt-get install --no-install-recommends -y \
    libjpeg-dev=1:1.5.2-2+deb10u1 \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

COPY --from=compile-image /venv /venv

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

ENV PATH="/venv/bin:$PATH"
CMD ["/bin/bash", "-c", "/entrypoint.sh"]