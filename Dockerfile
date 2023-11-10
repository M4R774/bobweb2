FROM python:3.10-bullseye AS builder
WORKDIR /

ENV DOCKER_BUILDKIT 1
ENV PYTHONUNBUFFERED 1

# Install Rust toolchain for tiktoken
# Tiktoken requires Rust toolchain, so build it in a separate stage. Pipefail: hadolint DL4006
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y

# Set required PATH
ENV PATH="/root/.cargo/bin:${PATH}"

COPY requirements.txt requirements.txt

##=========
# Firefox + Geckodriver for Raspberry + other libraries.
##=========
RUN apt-get update -qqy && \
    apt-get -y install --no-install-recommends \
      libgeos-dev=3.9.0-1 \
      firefox-esr=115.4.0esr-1~deb11u1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    curl https://github.com/jamesmortensen/geckodriver-arm-binaries/releases/download/v0.33.0/geckodriver-v0.33.0-linux-armv7l.tar.gz --location --output /tmp/geckodriver.tar.gz && \
    tar -C /tmp -zxf /tmp/geckodriver.tar.gz && \
    pip3 install --no-cache-dir -r requirements.txt

# Fetch static ffmpeg files for current architecture. Check https://johnvansickle.com/ffmpeg/
RUN curl https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-$(dpkg --print-architecture)-static.tar.xz --location --output /tmp/ffmpeg.tar.xz && \
    tar -C /tmp -zxf /tmp/ffmpeg.tar.xz



##========= New running image as the last step
FROM python:3.10-slim-bullseye
WORKDIR /

### Copy ffmpeg
### Copy ffmpeg and its required libraries
COPY --from=builder /tmp/ffmpeg*/ffmpeg /usr/bin/ffmpeg
COPY --from=builder /tmp/ffmpeg*/ffprobe /usr/bin/ffprobe

# Copy geckodriver and firefox from first step
COPY --from=builder /tmp/geckodriver /usr/local/bin/geckodriver
COPY --from=builder /usr/bin/firefox /usr/bin/firefox

## Copy installed python packages
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
#COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /usr/lib/*-linux-gnu* /usr/lib
#COPY --from=builder /usr/*-linux-gnu* /usr/lib



# Creates folders for both expected architectures and then creates symbolic links to those folders
RUN mkdir -p /usr/lib/arm-linux-gnueabihf && \
#    mkdir -p /lib/arm-linux-gnueabihf && \
    ln -s /usr/lib /usr/lib/arm-linux-gnueabihf && \
#    ln -s /usr/lib /lib/arm-linux-gnueabihf && \
    mkdir -p /usr/lib/x86_64-linux-gnu && \
#    mkdir -p /lib/x86_64-linux-gnu && \
    ln -s /usr/lib /usr/lib/x86_64-linux-gnu
#    ln -s /usr/lib /lib/x86_64-linux-gnu

# Add new user without root priviledges and use that
RUN groupadd -r user && useradd -r -g user user

# Copy bobweb and give user ownership of that directory
COPY bobweb bobweb
RUN chown -R user:user /bobweb
COPY entrypoint.sh .

USER user

CMD ["/bin/bash", "-c", "/entrypoint.sh"]
