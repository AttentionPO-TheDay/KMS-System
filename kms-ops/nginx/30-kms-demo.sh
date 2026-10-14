#!/bin/sh
set -eu
# Render only the gateway secret, never nginx variables such as $uri/$scheme.
if [ "${KMS_DEMO_ENABLED:-false}" = "true" ]; then
    case "${INTERNAL_TOKEN:-}" in
        ''|*[!A-Za-z0-9_-]*) printf '%s\n' 'INTERNAL_TOKEN must be a nonempty URL-safe token for demo gateway' >&2; exit 1;;
    esac
    envsubst '${INTERNAL_TOKEN}' < /etc/nginx/snippets/kms-demo-proxy.conf.template > /etc/nginx/snippets/kms-demo-proxy.conf
    cp /etc/nginx/kms-demo.template /etc/nginx/kms-demo.conf
    chmod 600 /etc/nginx/snippets/kms-demo-proxy.conf
else
    printf '%s\n' 'server { listen 80 default_server; listen 8088 default_server; listen 443 ssl default_server; server_name _; ssl_certificate /etc/nginx/tls/localhost.crt; ssl_certificate_key /etc/nginx/tls/localhost.key; return 404; }' > /etc/nginx/kms-demo.conf
fi
chmod 600 /etc/nginx/kms-demo.conf
