#!/bin/sh
set -eu
# 默认关闭。动态生成片段而不是把秘密烘焙进镜像；envsubst 只替换这一项，
# 不能把 nginx 的 $uri/$host 当作空环境变量抹掉。
if [ "${KMS_DEMO_ENABLED:-false}" = "true" ]; then
    case "${INTERNAL_TOKEN:-}" in
        ''|*[!A-Za-z0-9_-]*) printf '%s\n' 'INTERNAL_TOKEN must be a nonempty URL-safe token for demo gateway' >&2; exit 1;;
    esac
    envsubst '${INTERNAL_TOKEN}' < /etc/nginx/kms-demo.template > /etc/nginx/kms-demo.conf
else
    printf '%s\n' 'server { listen 8088; server_name _; return 404; }' > /etc/nginx/kms-demo.conf
fi
chmod 600 /etc/nginx/kms-demo.conf
