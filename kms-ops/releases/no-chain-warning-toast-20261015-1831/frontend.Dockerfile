FROM kms-gateway-nginx:before-no-chain-warning-toast-20261015-1831
COPY dist/ /usr/share/nginx/html/updatedel/
RUN find /usr/share/nginx/html/updatedel -type d -exec chmod 755 {} + \
    && find /usr/share/nginx/html/updatedel -type f -exec chmod 644 {} +
