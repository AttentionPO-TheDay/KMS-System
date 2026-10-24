#!/usr/bin/env python3
"""Provision external client credentials without replacing existing encryption keys."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import secrets


def write_new(path, text):
    descriptor = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        stream.write(text)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--client', required=True)
    args = parser.parse_args()
    if not re.fullmatch('[A-Za-z0-9_.-]{1,64}', args.client):
        parser.error('client 仅接受 1–64 位字母、数字、点、下划线和连字符')
    directory = args.directory.resolve()
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    config_file, token_file = directory / 'config.json', directory / (args.client + '.token')
    if config_file.exists():
        config = json.loads(config_file.read_text(encoding='utf-8'))
        if len(base64.urlsafe_b64decode(config['encryptionKey'])) != 32 or not isinstance(config['clients'], dict):
            parser.error('已有配置不合法；不会覆盖或重建加密密钥')
    else:
        # A missing configuration with existing token files may indicate lost encryption material.
        if any(directory.iterdir()):
            parser.error('目录非空但 config.json 缺失；请恢复原配置，禁止重新生成加密密钥')
        config = {'encryptionKey': base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), 'clients': {}}
    if args.client in config['clients']:
        if not token_file.is_file() or hashlib.sha256(token_file.read_text().strip().encode()).hexdigest() != config['clients'][args.client]:
            parser.error('已有客户端令牌缺失或不匹配；不会静默替换')
        print('客户端已存在，已保留原令牌和加密配置：' + str(token_file))
        return
    token = secrets.token_urlsafe(32)
    write_new(token_file, token + '\n')
    config['clients'][args.client] = hashlib.sha256(token.encode()).hexdigest()
    temporary = directory / 'config.json.new'
    write_new(temporary, json.dumps(config, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, config_file)
    print('已生成接入令牌文件：' + str(token_file))
    print('只向对应调用平台交付该 .token 文件；config.json 留在服务器并备份。')


if __name__ == '__main__': main()
