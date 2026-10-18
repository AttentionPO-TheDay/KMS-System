FROM kms-gateway-nginx:before-pool-sender-falcon-20261015-1807
COPY dist/ /usr/share/nginx/html/updatedel/
RUN find /usr/share/nginx/html/updatedel -type d -exec chmod 755 {} + \
    && find /usr/share/nginx/html/updatedel -type f -exec chmod 644 {} +
