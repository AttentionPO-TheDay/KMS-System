#!/usr/bin/env python3
"""Update the browser key-generation page and its node-registration backend."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from query_confirmed import container, environment, request

HERE = Path(__file__).resolve().parent
IMAGES = {'dvadmin3-django': 'kms-dvadmin3-django:node-keygen-did-20261020',
          'nginx': 'kms-gateway-nginx:node-keygen-did-20261020'}


def run(args, timeout=240):
    result = subprocess.run(args, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, args[:3])) + '; command output withheld')
    return result.stdout


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def write(path, value):
    path.write_bytes(value)
    os.chmod(path, 0o600)


def enabled_overlay(original, chain_id):
    updated = json.loads(json.dumps(original))
    for name, image in IMAGES.items():
        updated['services'].setdefault(name, {})['image'] = image
    env = updated['services']['dvadmin3-django'].setdefault('environment', {})
    env.update(FABRIC_DID_NODE_KEYGEN_ENABLED='true', FABRIC_DID_CHAIN_ID=chain_id,
               FABRIC_DID_BRIDGE_URL='http://fabric-did-bridge:9094/internal/fabric-did')
    return updated


CHECK = '''import json, os
from django.urls import resolve
from django.db import connection
from pqkds.models import NodeKeyDidRecord
print(json.dumps({'enabled':os.environ.get('FABRIC_DID_NODE_KEYGEN_ENABLED')=='true',
'route':resolve('/api/pqkds/node-self/keys/did/').url_name,
'schemaReady':NodeKeyDidRecord._meta.db_table in connection.introspection.table_names()}))
'''


def status():
    code, reply = request(container(), '/internal/fabric-did/status')
    state = reply.get('data', {})
    print('DID_CONFIG ' + json.dumps({name: state.get(name) for name in ('status', 'configured', 'writeEnabled')}, ensure_ascii=False))
    backend = json.loads(run(['docker', 'exec', 'dvadmin3-django', '/opt/venv/bin/python',
                              'manage.py', 'shell', '-c', CHECK]).decode().strip().splitlines()[-1])
    run(['docker', 'exec', 'kms_gateway', 'sh', '-c',
         "grep -ql 'node-self/keys/did/' /usr/share/nginx/html/updatedel/assets/*.js"])
    run(['docker', 'exec', 'kms_gateway', 'nginx', '-t'])
    expected = json.loads((HERE / 'image-ids.json').read_text())
    images_ok = all(container(name)['Image'] == expected[image] for name, image in
                    (('dvadmin3-django', IMAGES['dvadmin3-django']), ('kms_gateway', IMAGES['nginx'])))
    print('NODE_KEYGEN_DID ' + json.dumps(backend, ensure_ascii=False))
    passed = (code == 200 and state.get('status') == 'READY' and state.get('writeEnabled') is True
              and backend.get('enabled') is True and backend.get('schemaReady') is True
              and backend.get('route') == 'node-self-key-did' and images_ok)
    if passed:
        print('[READY] 已接通现有“密钥生成”页面；新生成后在算法卡片查看完整SysPid、查询状态和交易详情。')
        print('[INFO] 安装未提交交易。请在原浏览器页面生成一把新密钥，DID三项确认通过才算真实上链成功。')
    return 0 if passed else 2


def install(base):
    base = base.resolve()
    overlay = base / 'docker-compose.did-channel4.yml'
    if not overlay.is_file() or not (base / 'deploy.sh').is_file():
        raise RuntimeError('Specify the existing main deployment directory with the DID addon already installed')
    if overlay.name not in (base / 'deploy.sh').read_text(encoding='utf-8-sig'):
        raise RuntimeError('Main deploy.sh does not load the DID overlay')
    for line in (HERE / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        expected, name = line.split('  ', 1)
        if '/' in name or '\\' in name or digest(HERE / name) != expected:
            raise RuntimeError('Package checksum mismatch')
    code, reply = request(container(), '/internal/fabric-did/status')
    state = reply.get('data', {})
    required_bridge = (HERE / 'required-bridge-id.txt').read_text().strip()
    if (code != 200 or state.get('status') != 'READY' or state.get('writeEnabled') is not True
            or not state.get('chainId') or container()['Image'] != required_bridge):
        raise RuntimeError('Install the previous keygen DID bridge package first; the SysPid prepare API is required')
    compose = ['docker', 'compose', '-f', str(base / 'docker-compose.yml')]
    fisco = base / 'docker-compose.fisco-enabled.yml'
    if fisco.is_file():
        compose += ['-f', str(fisco)]
    compose += ['-f', str(overlay), '--profile', 'fabric-did']
    before = json.loads(run(compose + ['config', '--format', 'json']))['services']
    if before['dvadmin3-django']['environment'].get('INTERNAL_TOKEN') != environment(container()).get('INTERNAL_TOKEN'):
        raise RuntimeError('Django and DID internal credentials differ; check deployment configuration')
    run(['docker', 'load', '-i', str(HERE / 'kms-node-keygen-did-images.tar')], timeout=600)
    expected_images = json.loads((HERE / 'image-ids.json').read_text())
    for image, expected in expected_images.items():
        if run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}']).decode().strip() != expected:
            raise RuntimeError('Imported image does not match manifest')
    original = overlay.read_bytes()
    proposed = enabled_overlay(json.loads(original), state['chainId'])
    backup = base / ('node-keygen-did-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(mode=0o700)
    write(backup / overlay.name, original)
    try:
        write(overlay, (json.dumps(proposed, indent=2) + '\n').encode())
        after = json.loads(run(compose + ['config', '--format', 'json']))['services']
        for name, service in before.items():
            if name not in IMAGES and after.get(name) != service:
                raise RuntimeError('Unexpected change to an unrelated service')
        for name in IMAGES:
            for field in ('ports', 'volumes', 'command', 'entrypoint'):
                if before[name].get(field) != after[name].get(field):
                    raise RuntimeError('Unexpected change to existing service runtime configuration')
            for flag in ('KMS_CHAIN_BACKEND', 'KMS_CHAIN_WRITES_ENABLED', 'KMS_CHAIN_CONSUMER_ENABLED'):
                if before[name].get('environment', {}).get(flag) != after[name].get('environment', {}).get(flag):
                    raise RuntimeError('Unexpected change to the existing business chain route')
    except Exception:
        write(overlay, original)
        raise
    run(compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', *IMAGES])
    print('[INFO] 已更新节点登记后端和页面网关，等待增量迁移及服务启动。', flush=True)
    for _ in range(60):
        try:
            result = run(['docker', 'exec', 'dvadmin3-django', '/opt/venv/bin/python',
                          'manage.py', 'shell', '-c', CHECK], timeout=10).decode().strip().splitlines()[-1]
            check = json.loads(result)
            run(['docker', 'exec', 'dvadmin3-django', '/opt/venv/bin/python', '-c',
                 "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ws/',timeout=2)"], timeout=5)
            if check.get('schemaReady') and check.get('enabled'):
                break
        except (RuntimeError, OSError, subprocess.TimeoutExpired, ValueError, IndexError):
            pass
        time.sleep(2)
    else:
        raise RuntimeError('Startup timed out; inspect docker logs --tail=30 dvadmin3-django')
    print('[OK] 现有页面生成入口已更新，旧密钥与浏览器私钥保留。', flush=True)
    return status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'status'))
    parser.add_argument('--base', type=Path)
    args = parser.parse_args()
    if args.action == 'install' and args.base is None:
        parser.error('install requires --base')
    os.umask(0o077)
    try:
        return install(args.base) if args.action == 'install' else status()
    except Exception as exc:
        print('[ERROR] ' + (str(exc) if isinstance(exc, RuntimeError) else type(exc).__name__ + '; inspect the named service'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
