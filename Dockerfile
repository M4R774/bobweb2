FROM python:3.10-bullseye as builder

ENV DOCKER_BUILDKIT 1
ENV PYTHONUNBUFFERED 1

WORKDIR /

# Install Rust toolchain for tiktoken
# Tiktoken requires Rust toolchain, so build it in a separate stage
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y

# Set required PATH
ENV PATH="/root/.cargo/bin:${PATH}"


#=========
# Firefox + Geckodriver for Raspberry + other libraries.
#=========
RUN --mount=type=cache,target=/root/.cache \
    apt-get update -qqy && apt-get -y install --no-install-recommends \
      wget libc6 libgeos-dev=3.9.0-1 ffmpeg=7:4.3.6-0+deb11u1 ; \
    wget --progress=dot:giga https://snapshot.debian.org/archive/debian/20231104T151024Z/pool/main/f/firefox/firefox_119.0-1_"$(dpkg --print-architecture)".deb -O firefox.deb ; \
    apt-get -y install ./firefox.deb ; \
    # Cleanup
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /firefox.deb

# Install geckodriver from either unofficial arm package or official x64 package
RUN --mount=type=cache,target=/var/cache/apt \
    if [ "$(uname -m)" = armv7l ]; then \
      # Run only if ARM architecture. Uses unofficial arm build \
      url="https://github.com/jamesmortensen/geckodriver-arm-binaries/releases/download/v0.33.0/geckodriver-v0.33.0-linux-armv7l.tar.gz" ; \
    else \
      url="https://github.com/mozilla/geckodriver/releases/download/v0.33.0/geckodriver-v0.33.0-linux64.tar.gz" ; \
    fi; \
    wget --progress=dot:giga -O /tmp/geckodriver.tar.gz ${url} ; \
    tar -C /tmp -zxf /tmp/geckodriver.tar.gz ; \
    mkdir -p /opt/geckodriver-bin ; \
    mv /tmp/geckodriver /opt/geckodriver-bin/geckodriver ; \
    echo "Symlinking geckodriver to /usr/local/bin/geckodriver" ; \
    ln -s /opt/geckodriver-bin/geckodriver /usr/local/bin/geckodriver ; \
    chmod 755 /usr/local/bin/geckodriver ; \
    rm /tmp/geckodriver.tar.gz


COPY requirements.txt requirements.txt

# Install required pip packages
RUN --mount=type=cache,target=/var/cache/apt \
    if [ "$(uname -m)" = armv7l ]; \
      # Run only if ARM architecture
      then pip3 install --no-cache-dir Adafruit-DHT==1.4.0 RPi.GPIO==0.7.1 --install-option '--force-pi'; \
    fi ; \
    pip3 install --no-cache-dir -r requirements.txt

#========= New running image as second step
#FROM python:3.10-slim-bullseye

#WORKDIR /

# Copy geckodriver and do symlinking
#COPY --from=builder /opt/geckodriver-bin/geckodriver /opt/geckodriver-bin/geckodriver

# Copy installed packages
#COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
#COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy ffmpeg
#COPY --from=builder /usr/bin/ffmpeg /usr/bin/ffprobe /usr/bin/ffplay /usr/bin/

#RUN --mount=type=cache,target=/root/.cache \
#    apt-get update -qqy && apt-get -y install --no-install-recommends ffmpeg=7:4.3.6-0+deb11u1

COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
