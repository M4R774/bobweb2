FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

# Install Rust toolchain for tiktoken
# Tiktoken requires Rust toolchain, so build it in a separate stage. Pipefail: hadolint DL4006
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y

# Set required PATH
ENV PATH="/root/.cargo/bin:${PATH}"

#=========
# Firefox + Geckodriver for Raspberry + other libraries
#=========
RUN apt-get update -qqy \
    && apt-get -y install --no-install-recommends \
    libgeos-dev=3.9.0-1 ffmpeg=7:4.3.6-0+deb11u1 libavcodec-extra=7:4.3.6-0+deb11u1 ; \
    curl https://snapshot.debian.org/archive/debian/20221231T090612Z/pool/main/f/firefox/firefox_108.0-2_"$(dpkg --print-architecture)".deb \
      --location --output firefox.deb \
    && apt-get -y install --no-install-recommends ./firefox.deb \
    && rm -rf /var/lib/apt/lists/* /var/cache/apt/* ./firefox.deb ; \
    curl https://github.com/jamesmortensen/geckodriver-arm-binaries/releases/download/v0.32.0/geckodriver-v0.32.0-linux-armv7l.tar.gz \
      --location --output /tmp/geckodriver.tar.gz; \
    tar -C /tmp -zxf /tmp/geckodriver.tar.gz ; \
    rm /tmp/geckodriver.tar.gz ; \
    mkdir -p /opt/geckodriver-bin ; \
    mv /tmp/geckodriver /opt/geckodriver-bin/geckodriver ; \
    echo "Symlinking geckodriver to /usr/local/bin/geckodriver" ; \
    ln -s /opt/geckodriver-bin/geckodriver /usr/local/bin/geckodriver ; \
    chmod 755 /usr/local/bin/geckodriver

COPY requirements.txt requirements.txt

RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
