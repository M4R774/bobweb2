FROM python:3.10-slim-buster

ENV PYTHONUNBUFFERED 1

WORKDIR /

RUN apt-get update -y && apt-get install -y gcc libjpeg-dev zlib1g zlib1g-dev

COPY requirements.txt requirements.txt
RUN pip3 install --no-cache-dir -r requirements.txt

# take only needed modules and starting script to the final image
COPY bobweb bobweb
COPY entrypoint.sh .

CMD ["/bin/bash", "-c", "/entrypoint.sh"]