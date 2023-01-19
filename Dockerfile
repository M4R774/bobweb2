FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED 1

WORKDIR /

#=========
# Firefox for Raspberry
#=========
RUN echo "deb http://deb.debian.org/debian/ sid main" >> /etc/apt/sources.list \
  && apt-get update -qqy \
  && apt-get install libavcodec-extra -y \
  && wget https://snapshot.debian.org/archive/debian/20221231T090612Z/pool/main/f/firefox/firefox_108.0-2_`dpkg --print-architecture`.deb -O firefox.deb \
  && apt install ./firefox.deb -y \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/* ./firefox.deb

#=============
# Geckodriver that matches Firefox
#=============
RUN wget --no-verbose -O /tmp/geckodriver.tar.gz https://github.com/jamesmortensen/geckodriver-arm-binaries/releases/download/v0.32.0/geckodriver-v0.32.0-linux-armv7l.tar.gz ; \
    tar -C /tmp -zxf /tmp/geckodriver.tar.gz ; \
    rm /tmp/geckodriver.tar.gz ; \
    mkdir -p /opt/geckodriver-bin ; \
    mv /tmp/geckodriver /opt/geckodriver-bin/geckodriver ; \
    echo "Symlinking geckodriver to /usr/local/bin/geckodriver" ; \
    ln -s /opt/geckodriver-bin/geckodriver /usr/local/bin/geckodriver ; \
    chmod 755 /usr/local/bin/geckodriver

RUN apt-get update -y && apt-get -y install --no-install-recommends \
    libgeos-dev=3.9.0-1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]