#!/bin/bash
# 独立的上传完整性检查（不依赖 deploy.sh 的版本）。
# 逐个核对镜像构建与运行所需的文件 —— FTP 漏传时，docker build 的报错很难懂，
# 这里直接点名缺了哪个。
miss=0
for f in \
  runtime/generate-java/kms-generate.jar \
  runtime/generate-java/config-fisco.toml \
  runtime/updatedel-java/kms-updatedel.jar \
  runtime/updatedel-java/config-fisco.toml \
  runtime/generate-go/kms-generate-service \
  runtime/updatedel-go/kms-updatedel-service \
  runtime/acceptance-go/kms-acceptance-backend \
  runtime/acceptance-go/security/security_test.sh \
  front/updatedel/index.html front/user/index.html front/acceptance/index.html \
  build/generate-java.Dockerfile build/updatedel-java.Dockerfile \
  build/generate-go.Dockerfile build/updatedel-go.Dockerfile \
  build/acceptance-go.Dockerfile build/nginx.Dockerfile \
  portal/index.html mysql/my.cnf mysql/init \
  nginx/nginx.conf nginx/snippets \
  fisco/console/conf/ca.crt fisco/console/conf/sdk.crt fisco/console/conf/sdk.key \
  nodes/127.0.0.1/fisco-bcos \
  nodes/127.0.0.1/node0/conf/group.1.genesis \
  nodes/127.0.0.1/node0/conf/channel_cert/ca.crt \
  "../kms-distribute/extracted/ruoyi (2)/backend/start.sh" \
  "../kms-distribute/extracted/ruoyi (2)/requirements.txt" \
  "../kms-distribute/extracted/ruoyi (2)/docker_env/django/Dockerfile" ; do
  if [ -e "$f" ]; then printf '  [ok]   %s\n' "$f"
  else printf '  [缺]   %s\n' "$f"; miss=$((miss+1)); fi
done
echo
if [ "$miss" -eq 0 ]; then echo "上传完整：可以构建"; else echo "有 $miss 项缺失：先补齐再构建（构建必定失败）"; fi