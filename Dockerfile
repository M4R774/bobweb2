# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.15-slim-trixie

# Build stage: compilers are only needed here to build wheels (e.g. on armv7l where prebuilt wheels
# are scarce). Only the resulting virtualenv is copied to the final images.
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS builder

WORKDIR /

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# hadolint ignore=DL3008
RUN apt-get update -qqy \
    && apt-get -y install --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

COPY requirements.txt requirements.txt

RUN if [ "$(uname -m)" = armv7l ]; then \
    # --force-pi is needed for Adafruit-DHT when installing on any other armv7l platform
    # other than Raspberry Pi, for example when building multi-arch docker image.
    pip install Adafruit-DHT==1.4.0 --config-settings="--build-option=--force-pi"; \
    fi \
    && pip install -r requirements.txt

# Test stage dependencies on top of the production ones. Not part of the final image.
FROM builder AS test-builder
WORKDIR /
COPY requirements-dev.txt requirements-dev.txt
RUN pip install -r requirements-dev.txt

# Shared runtime base: slim image with only runtime system packages and a non-root user.
# hadolint ignore=DL3006
FROM ${PYTHON_IMAGE} AS base

ENV PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:${PATH}"

# hadolint ignore=DL3008
RUN apt-get update -qqy \
    && apt-get -y install --no-install-recommends \
      ffmpeg \
      libavcodec-extra \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* \
    && useradd --create-home --uid 1000 app \
    # Writable directory for runtime files, e.g. the telethon session file. Note that ownership of '/' itself
    # is not preserved in image layers, so it can't be used for this.
    && mkdir /data && chown app:app /data

ENV SESSION_DIR=/data

WORKDIR /

# Test image: `docker build --target test .`
FROM base AS test
COPY --from=test-builder /opt/venv /opt/venv
COPY --chown=app:app bot bot
COPY --chown=app:app web web
COPY --chown=app:app entrypoint.sh .
USER app
CMD ["python", "-u", "web/manage.py", "test"]

# Production image (default, must remain the last stage)
FROM base AS runtime
COPY --from=builder /opt/venv /opt/venv
# take only needed modules and starting script to the final image
COPY --chown=app:app bot bot
COPY --chown=app:app web web
COPY --chown=app:app entrypoint.sh .

# Embed latest commit information to the image if given as build parameters.
# These are positioned to be set just before the entrypoint command as these
# values change each time causing cache invalidation on subsequent layers.
ARG COMMIT_MESSAGE
ARG COMMIT_AUTHOR_NAME
ARG COMMIT_AUTHOR_EMAIL
# Set environment variables for runtime, converting file back to environment variable
ENV COMMIT_MESSAGE=${COMMIT_MESSAGE}
ENV COMMIT_AUTHOR_NAME=${COMMIT_AUTHOR_NAME}
ENV COMMIT_AUTHOR_EMAIL=${COMMIT_AUTHOR_EMAIL}

USER app

CMD ["/entrypoint.sh"]
