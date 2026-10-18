FROM kms-gateway-nginx:before-group-agreement-20261014
COPY dist/ /usr/share/nginx/html/updatedel/
RUN find /usr/share/nginx/html/updatedel -type d -exec chmod 755 {} + \
    && find /usr/share/nginx/html/updatedel -type f -exec chmod 644 {} +
