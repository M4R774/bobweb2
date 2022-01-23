FROM python:3.10-slim-buster

RUN apt update
RUN apt install git -y
COPY requirements.txt requirements.txt
RUN pip3 install -r requirements.txt

COPY . .
CMD /entrypoint.sh
