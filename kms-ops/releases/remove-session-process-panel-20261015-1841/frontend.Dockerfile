FROM kms-gateway-nginx:before-remove-session-process-panel-20261015-1841
COPY dist/ /usr/share/nginx/html/updatedel/
RUN find /usr/share/nginx/html/updatedel -type d -exec chmod 755 {} + \
    && find /usr/share/nginx/html/updatedel -type f -exec chmod 644 {} +
