FROM python:3.10-bullseye as builder

ENV DOCKER_BUILDKIT 1
ENV PYTHONUNBUFFERED 1

WORKDIR /

# Install Rust toolchain for tiktoken
# Tiktoken requires Rust toolchain, so build it in a separate stage
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y

# Set required PATH
ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt requirements.txt

##=========
# Firefox + Geckodriver for Raspberry + other libraries.
##=========
RUN --mount=type=cache,target=/root/.cache \
    # Install libgeos
    apt-get update -qqy && apt-get -y install --no-install-recommends libgeos-dev=3.9.0-1 ; \
    # Download and decompress geckodriver from either unofficial arm package or official x64 package
    if [ "$(uname -m)" = armv7l ]; then \
      # Run only if ARM architecture. Uses unofficial arm build \
      url="https://github.com/jamesmortensen/geckodriver-arm-binaries/releases/download/v0.33.0/geckodriver-v0.33.0-linux-armv7l.tar.gz" ; \
    else \
      url="https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux64.tar.gz" ; \
    fi; \
    wget --progress=dot:giga -O /tmp/geckodriver.tar.gz ${url} ; \
    tar -C /tmp -zxf /tmp/geckodriver.tar.gz ; \
    # Install required pip packages
    if [ "$(uname -m)" = armv7l ]; \
      # Additional packages that are installed only on raspberry pi
      then pip3 install --no-cache-dir Adafruit-DHT==1.4.0 RPi.GPIO==0.7.1 --install-option '--force-pi'; \
    fi ; \
    pip3 install --no-cache-dir -r requirements.txt



##========= Image that contains ffmpeg. All ffmpeg libraries are copied to the final image
FROM python:3.10-slim-bullseye as ffmpeg
WORKDIR /
RUN apt-get update -qqy \
    && apt-get -y install --no-install-recommends ffmpeg=7:4.3.6-0+deb11u1 libavcodec-extra=7:4.3.6-0+deb11u1



##========= New running image as the last step
FROM python:3.10-slim-bullseye
WORKDIR /

# Copy geckodriver from first step
COPY --from=builder /tmp/geckodriver /usr/local/bin/geckodriver

# Install Firefox
RUN apt-get update -qqy && apt-get -y install --no-install-recommends firefox-esr=115.4.0esr-1~deb11u1 &&  \
    apt-get clean && rm -rf /var/lib/apt/lists/*

## Copy installed python packages
COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

### Copy ffmpeg and its required libraries
COPY --from=ffmpeg /usr/bin/ffmpeg /usr/bin/ffprobe /usr/bin/ffplay /usr/bin/
COPY --from=ffmpeg /usr/lib/*-linux-gnu/* /usr/lib/
COPY --from=ffmpeg /lib/*-linux-gnu/* /usr/lib/

COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
