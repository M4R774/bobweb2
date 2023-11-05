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



##========= New running image as second step
#FROM python:3.10-bullseye
#
#WORKDIR /

#COPY --from=builder /usr/local/lib/python3.10/site-packages/ /usr/local/lib/python3.10/site-packages/
#COPY --from=builder /usr/local/bin/ /usr/local/bin/

#=========
# Firefox + Geckodriver for Raspberry + other libraries.
# Uses colon instead of douple amperson as separator as some steps may fail
#=========
RUN --mount=type=cache,target=/root/.cache \
    wget --progress=dot:giga https://snapshot.debian.org/archive/debian/20221231T090612Z/pool/main/f/firefox/firefox_108.0-2_"$(dpkg --print-architecture)".deb -O firefox.deb ; \
    apt-get update -qqy && apt-get -y install --no-install-recommends ; \
      libgeos-dev=3.9.0-1 ffmpeg=7:4.3.6-0+deb11u1 ./firefox.deb ; \
    # Install geckodriver and symlink it
    wget --progress=dot:giga -O /tmp/geckodriver.tar.gz https://github.com/jamesmortensen/geckodriver-arm-binaries/releases/download/v0.32.0/geckodriver-v0.32.0-linux-armv7l.tar.gz ; \
    tar -C /tmp -zxf /tmp/geckodriver.tar.gz ; \
    mkdir -p /opt/geckodriver-bin ; \
    mv /tmp/geckodriver /opt/geckodriver-bin/geckodriver ; \
    echo "Symlinking geckodriver to /usr/local/bin/geckodriver" ; \
    ln -s /opt/geckodriver-bin/geckodriver /usr/local/bin/geckodriver ; \
    chmod 755 /usr/local/bin/geckodriver ; \
    # Cleanup
    apt-get clean && rm -rf /var/lib/apt/lists/* /var/cache/apt/* /firefox.deb /tmp/geckodriver.tar.gz ; \
    # Install required pip packages
    if [ "$(uname -m)" = armv7l ]; \
      # Run only if ARM architecture
      then pip3 install --no-cache-dir Adafruit-DHT==1.4.0 RPi.GPIO==0.7.1 --install-option '--force-pi'; \
    fi ; \
    pip3 install --no-cache-dir -r requirements.txt

COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
