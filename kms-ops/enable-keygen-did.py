#!/usr/bin/env python3
"""Install the user-key generation DID update without changing other chain routes."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from query_confirmed import container, environment, request

HERE = Path(__file__).resolve().parent
IMAGES = {
    'fabric-did-bridge': 'kms-fabric-did:keygen-20261020',
    'generate-go': 'kms-generate-go:did-keygen-20261020',
    'generate-java': 'kms-generate-java:did-keygen-20261020',
}
WRITE_FLAGS = ('KMS_CHAIN_WRITES_ENABLED', 'FABRIC_DID_WRITE_ENABLED', 'FABRIC_DID_CREATE_POLICY_APPROVED')


def run(args, data=None):
    result = subprocess.run(args, input=data, capture_output=True, timeout=240)
    if result.returncode:
        raise RuntimeError('Command failed: ' + ' '.join(map(str, args[:3])) + '; credentials and command output withheld')
    return result.stdout


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def write(path, data):
    path.write_bytes(data)
    os.chmod(path, 0o600)


def enabled_overlay(original):
    updated = json.loads(json.dumps(original))
    services = updated['services']
    bridge = services['fabric-did-bridge']
    bridge['image'] = IMAGES['fabric-did-bridge']
    bridge['environment'].update({flag: 'true' for flag in WRITE_FLAGS})
    for service in ('generate-go', 'generate-java'):
        target = services.setdefault(service, {})
        target['image'] = IMAGES[service]
        env = target.setdefault('environment', {})
        env['FABRIC_DID_BRIDGE_URL'] = 'http://fabric-did-bridge:9094/internal/fabric-did'
        if service == 'generate-go':
            env['FABRIC_DID_KEYGEN_ENABLED'] = 'true'
    return updated


def status():
    code, reply = request(container(), '/internal/fabric-did/status')
    state = reply.get('data', {})
    public = {key: state.get(key) for key in ('status', 'enabled', 'configured', 'writeEnabled', 'missingFields')}
    print('DID_CONFIG ' + json.dumps(public, ensure_ascii=False), flush=True)
    go = environment(container('kms_generate_go'))
    enabled = go.get('FABRIC_DID_KEYGEN_ENABLED') == 'true'
    print('KEYGEN_DID_ENABLED=' + str(enabled).lower(), flush=True)
    images_match = all(container(name)['Config']['Image'] == IMAGES[service] for service, name in
                       (('fabric-did-bridge', 'kms_fabric_did'), ('generate-go', 'kms_generate_go'),
                        ('generate-java', 'kms_generate_java')))
    passed = code == 200 and state.get('status') == 'READY' and state.get('writeEnabled') is True and enabled and images_match
    if passed:
        print('[READY] 用户密钥生成将分配独立SysPid并调用DID上链接口；真实交易以CONFIRMED核验结果为准。')
    return 0 if passed else 2


def query(sys_pid):
    if not re.fullmatch('[0-9a-f]{182}', sys_pid):
        raise RuntimeError('Invalid SysPid; use the complete value returned by generation')
    code, reply = request(container(), '/internal/fabric-did/sys-pids/verify', {'sysPid': sys_pid})
    data = reply.get('data', {})
    public = {key: data.get(key) for key in ('provider', 'chainId', 'sysPid', 'did', 'txId', 'status',
                                           'transactionValid', 'metadataMatches', 'errorCode')}
    print(json.dumps(public, ensure_ascii=False, indent=2), flush=True)
    passed = code == 200 and data.get('sysPid') == sys_pid and data.get('status') == 'CONFIRMED' and \
        data.get('transactionValid') is True and data.get('metadataMatches') is True
    print('[PASS] 本次生成对应的DID交易已确认。' if passed else '[NOT CONFIRMED] 请保留同一SysPid继续查询，不要重新生成替代记录。')
    return 0 if passed else 2


def install(base):
    base = base.resolve()
    overlay = base / 'docker-compose.did-channel4.yml'
    if not overlay.is_file() or not (base / '.env').is_file() or not (base / 'deploy.sh').is_file():
        raise RuntimeError('Install the original read-only DID addon first; specify its main deployment directory')
    if 'docker-compose.did-channel4.yml' not in (base / 'deploy.sh').read_text(encoding='utf-8-sig'):
        raise RuntimeError('Main deploy.sh does not load the channel4 addon')
    for line in (HERE / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
        expected, name = line.split('  ', 1)
        if '/' in name or '\\' in name or digest(HERE / name) != expected:
            raise RuntimeError('Package checksum mismatch')
    original = overlay.read_bytes()
    proposed = enabled_overlay(json.loads(original))
    compose = ['docker', 'compose', '-f', str(base / 'docker-compose.yml')]
    fisco = base / 'docker-compose.fisco-enabled.yml'
    if fisco.is_file():
        compose += ['-f', str(fisco)]
    compose += ['-f', str(overlay), '--profile', 'fabric-did']
    before = json.loads(run(compose + ['config', '--format', 'json']))['services']
    code, reply = request(container(), '/internal/fabric-did/status')
    if code != 200 or not reply.get('data', {}).get('configured'):
        raise RuntimeError('DID connection is not configured; complete the read-only addon first')
    database = before['generate-java']['environment'].get('DB_NAME', 'kms')
    if not re.fullmatch('[A-Za-z0-9_]+', database):
        raise RuntimeError('Unsupported database name')
    # Additive, repeatable schema update. Root password stays inside the MySQL container environment.
    mysql_name = before['mysql'].get('container_name', 'kms_mysql')
    run(['docker', 'exec', '-i', mysql_name, 'sh', '-c',
         'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; exec mysql -uroot --default-character-set=utf8mb4 "$1"',
         'sh', database], (HERE / '57_keygen_did_syspid.sql').read_bytes())
    run(['docker', 'load', '-i', str(HERE / 'kms-keygen-did-images.tar')])
    expected_images = json.loads((HERE / 'image-ids.json').read_text())
    for image, expected in expected_images.items():
        actual = run(['docker', 'image', 'inspect', image, '--format', '{{.Id}}']).decode().strip()
        if actual != expected:
            raise RuntimeError('Imported image does not match the package manifest')
    backup = base / ('did-keygen-backup-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    backup.mkdir(mode=0o700)
    write(backup / overlay.name, original)
    try:
        write(overlay, (json.dumps(proposed, indent=2) + '\n').encode())
        after = json.loads(run(compose + ['config', '--format', 'json']))['services']
        for name in before:
            if name not in IMAGES and after.get(name) != before[name]:
                raise RuntimeError('Unexpected change to an unrelated service; original config restored')
        for name in ('generate-go', 'generate-java'):
            for flag in ('KMS_CHAIN_WRITES_ENABLED', 'KMS_CHAIN_BACKEND', 'KMS_CHAIN_CONSUMER_ENABLED'):
                if after[name].get('environment', {}).get(flag) != before[name].get('environment', {}).get(flag):
                    raise RuntimeError('Unexpected change to the existing business chain route')
    except Exception:
        write(overlay, original)
        raise
    run(compose + ['up', '-d', '--no-deps', '--no-build', '--pull', 'never', '--force-recreate', *IMAGES])
    print('[INFO] 三个容器已更新，等待生成服务启动。', flush=True)
    for _ in range(50):
        try:
            code, _ = request(container(), '/health', authenticated=False)
            if code == 200:
                run(['docker', 'exec', 'kms_generate_go', 'curl', '--fail', '--silent', '--max-time', '2',
                     'http://127.0.0.1:8081/generate/ping'])
                run(['docker', 'exec', 'kms_generate_java', 'curl', '--fail', '--silent', '--max-time', '2',
                     'http://127.0.0.1:9081/generate/ping'])
                break
        except (OSError, RuntimeError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError('Service startup timed out; inspect docker logs --tail=30 for the three updated containers')
    print('[OK] 已更新DID、密钥生成Go和Java三个容器，并增加SysPid存储字段。', flush=True)
    print('[INFO] 未主动提交测试交易；请正常生成一把用户密钥，取得返回的SysPid后查询。', flush=True)
    return status()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('install', 'status', 'query'))
    parser.add_argument('--base', type=Path)
    parser.add_argument('--sys-pid')
    args = parser.parse_args()
    if args.action == 'install' and args.base is None:
        parser.error('install requires --base')
    if args.action == 'query' and not args.sys_pid:
        parser.error('query requires --sys-pid')
    os.umask(0o077)
    try:
        return install(args.base) if args.action == 'install' else query(args.sys_pid) if args.action == 'query' else status()
    except Exception as error:
        print('[ERROR] ' + (str(error) if isinstance(error, RuntimeError) else type(error).__name__ + '; inspect the named service'))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
