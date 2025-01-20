FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -qqy \
    && apt-get -y install --no-install-recommends \
      ffmpeg=7:4.3.8-0+deb11u1 \
      libavcodec-extra=7:4.3.8-0+deb11u1 \
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

# Embed latest commit information to the image if given as build parameters.
# These are positioned to be set just before the entrypoint command as these
# values change each time causing cache invalidation on subsequent layers.
ARG COMMIT_MESSAGE
ARG COMMIT_AUTHOR_NAME
ARG COMMIT_AUTHOR_EMAIL

# Using a helper file to process commit message
SHELL option -o pipefail
RUN echo -e "${COMMIT_MESSAGE}" | sed 's/\\n/\n/g' > /tmp/commit_message.txt

# Set environment variables for runtime, converting file back to environment variable
ENV COMMIT_MESSAGE=$(cat /tmp/commit_message.txt) \
    COMMIT_AUTHOR_NAME=${COMMIT_AUTHOR_NAME} \
    COMMIT_AUTHOR_EMAIL=${COMMIT_AUTHOR_EMAIL}

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
