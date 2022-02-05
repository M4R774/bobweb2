FROM nginx:1.21-alpine
RUN mkdir -p /etc/letsencrypt/live/martta.tk

RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d
