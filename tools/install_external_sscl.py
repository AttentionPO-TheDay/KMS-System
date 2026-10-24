#!/usr/bin/env python3
"""Install the external SM2/SSCL increment over the currently running KMS deployment."""
import argparse
import ast
from datetime import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import zipfile


def run(arguments, cwd=None):
    process = subprocess.run([str(x) for x in arguments], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if process.returncode:
        raise RuntimeError('Command failed: ' + str(arguments[0]) + '\n' + process.stdout[-3000:])
    return process.stdout


def rewrite_zip(source, updates):
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as archive, zipfile.ZipFile(output, 'w') as target:
        present = set()
        for info in archive.infolist():
            target.writestr(info, updates.get(info.filename, archive.read(info.filename)))
            present.add(info.filename)
        for name, data in updates.items():
            if name not in present:
                target.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()


def patch_jar(original, controller, generator):
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        libraries = [name for name in archive.namelist() if name.startswith('BOOT-INF/lib/ruoyi-system-') and name.endswith('.jar')]
        if len(libraries) != 1:
            raise RuntimeError('Unsupported generate JAR: expected one ruoyi-system library')
        library = libraries[0]
        nested = rewrite_zip(archive.read(library), {'com/ruoyi/generate/service/generator/SSCLGenerator.class': generator})
    return rewrite_zip(original, {library: nested, 'BOOT-INF/classes/com/ruoyi/generate/controller/InternalSsclController.class': controller})


def patch_models(source, block, profile):
    anchor = 'class NodeKeyDidRecord(models.Model):'
    if anchor not in source or 'class Node(CoreModel):' not in source:
        raise RuntimeError('This increment requires the installed node-key DID supplement (migration 0038)')
    if 'class ExternalNodeActivation(models.Model):' in source:
        start = source.index('class ExternalNodeActivation(models.Model):')
        stop = source.index(anchor, start)
        source = source[:start] + block + source[stop:]
    else:
        source = source.replace(anchor, block + anchor, 1)
    node = source.index('class Node(CoreModel):')
    end = source.find('\nclass ', node + 1)
    if 'initialization_profile =' not in source[node:end if end >= 0 else None]:
        source = source.replace('class Node(CoreModel):\n', 'class Node(CoreModel):\n' + profile, 1)
    else:
        source = source[:node] + re.sub(r'(?m)^    initialization_profile = [^\n]*\n', lambda _: profile,
                                      source[node:], count=1)
    ast.parse(source)
    return source


def patch_urls(source):
    if 'from pqkds.external_sscl_views import external_node_activation' not in source:
        anchor = 'from pqkds.demo_context import internal_node_context'
        if anchor not in source: raise RuntimeError('Unsupported application URL configuration')
        source = source.replace(anchor, anchor + '\nfrom pqkds.external_sscl_views import external_node_activation', 1)
    if 'external-api/v1/nodes/activate/' not in source:
        source, count = re.subn(r'(?m)^(\s*path\([\'"]internal/demo/node/[\'"].*\),)$',
            lambda match: match[0] + '\n            path("external-api/v1/nodes/activate/", external_node_activation, name="external-node-activation"),', source)
        if count != 1: raise RuntimeError('Unsupported application URL layout')
    ast.parse(source)
    return source


def patch_audit(source, block):
    if "path.rstrip('/') == '/external-api/v1/nodes/activate'" not in source:
        anchor = "    if '/node-self/keygen/' not in path and not path.rstrip('/').endswith('/node-self/keys'):"
        if source.count(anchor) != 1: raise RuntimeError('Unsupported public-key audit helper')
        source = source.replace(anchor, block + anchor, 1)
    ast.parse(source)
    return source


def bind(source, target):
    return {'type': 'bind', 'source': str(source), 'target': target, 'read_only': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='现有 docker-compose.yml 所在部署目录')
    parser.add_argument('--client', required=True, help='接入平台编号，例如 partner-a')
    parser.add_argument('--activate', action='store_true', help='执行新增迁移并重建三个服务；不传则只准备和校验')
    args = parser.parse_args()
    if os.name != 'posix': parser.error('请在 Linux 部署服务器执行')
    if not re.fullmatch('[A-Za-z0-9_.-]{1,64}', args.client): parser.error('client 格式不合法')
    package, root = Path(__file__).resolve().parent, args.root.resolve()
    if not (root / 'docker-compose.yml').is_file(): parser.error('部署目录缺少 docker-compose.yml')
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest.items():
        path = (package / name).resolve()
        if package not in path.parents or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise RuntimeError('Package checksum mismatch: ' + name)
    labels = json.loads(run(['docker', 'inspect', '-f', '{{json .Config.Labels}}', 'dvadmin3-django']))
    files = labels.get('com.docker.compose.project.config_files', '')
    project = labels.get('com.docker.compose.project', '')
    if not files or not project: raise RuntimeError('Cannot locate the active Compose configuration')
    original_files = [Path(path) for path in files.split(',')]
    if any(not path.is_file() for path in original_files): raise RuntimeError('An active Compose file is missing')
    overlay = root / 'docker-compose.external-sscl.yml'
    original_command = ['docker', 'compose', '--project-name', project]
    for file in original_files: original_command += ['-f', str(file)]
    command = ['docker', 'compose', '--project-name', project]
    for file in original_files:
        if file.resolve() != overlay: command += ['-f', str(file)]
    command += ['-f', str(overlay)]
    # Verify prerequisites using the existing container; do not read or print .env.
    migrations = run(['docker', 'exec', '-w', '/backend', 'dvadmin3-django', 'python', 'manage.py', 'showmigrations', 'pqkds'], cwd=root)
    if '[X] 0038_nodekeydidrecord' not in migrations:
        raise RuntimeError('Migration 0038 must already be applied before this increment')
    run(['docker', 'exec', 'dvadmin3-django', 'python', '-c', 'from cryptography.fernet import Fernet'])
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backup = root / 'external-sscl-backups' / stamp
    backup.mkdir(parents=True, mode=0o700)
    runtime = root / 'external-sscl-runtime' / stamp
    runtime.mkdir(parents=True, mode=0o755)
    sources = {
        'models.py': ('dvadmin3-django', '/backend/pqkds/models.py'),
        'urls.py': ('dvadmin3-django', '/backend/application/urls.py'),
        'middleware.py': ('dvadmin3-django', '/backend/dvadmin/utils/middleware.py'),
        'kms-generate.jar': ('kms_generate_java', '/app/kms-generate.jar'),
        'nginx.conf': ('kms_gateway', '/etc/nginx/nginx.conf'),
        'kms-demo-locations.conf': ('kms_gateway', '/etc/nginx/snippets/kms-demo-locations.conf'),
    }
    for name, (container, path) in sources.items(): run(['docker', 'cp', container + ':' + path, backup / name])
    previous_overlay = overlay.is_file()
    if previous_overlay: shutil.copy2(overlay, backup / 'previous-overlay.json')
    (runtime / 'models.py').write_text(patch_models((backup / 'models.py').read_text(encoding='utf-8'), (package / 'model-block.txt').read_text(encoding='utf-8'), (package / 'node-profile.txt').read_text(encoding='utf-8')), encoding='utf-8')
    (runtime / 'urls.py').write_text(patch_urls((backup / 'urls.py').read_text(encoding='utf-8')), encoding='utf-8')
    (runtime / 'middleware.py').write_text(patch_audit((backup / 'middleware.py').read_text(encoding='utf-8'), (package / 'audit-block.txt').read_text(encoding='utf-8')), encoding='utf-8')
    (runtime / 'kms-generate.jar').write_bytes(patch_jar((backup / 'kms-generate.jar').read_bytes(), (package / 'InternalSsclController.class').read_bytes(), (package / 'SSCLGenerator.class').read_bytes()))
    nginx = (backup / 'nginx.conf').read_text(encoding='utf-8')
    if 'zone=kms_external_sscl:' not in nginx:
        nginx, count = re.subn(r'(?m)^http\s*\{', 'http {\n    limit_req_zone $binary_remote_addr zone=kms_external_sscl:1m rate=2r/s;', nginx, count=1)
        if count != 1: raise RuntimeError('Unsupported nginx HTTP configuration')
    (runtime / 'nginx.conf').write_text(nginx, encoding='utf-8')
    locations = (backup / 'kms-demo-locations.conf').read_text(encoding='utf-8')
    if '/etc/nginx/snippets/kms-external-sscl.conf' not in locations:
        locations += '\ninclude /etc/nginx/snippets/kms-external-sscl.conf;\n'
    (runtime / 'kms-demo-locations.conf').write_text(locations, encoding='utf-8')
    for name in ('external_sscl.py', 'external_sscl_views.py', '0039_external_sscl_activation.py', '0040_external_sm2_profile.py', 'kms-external-sscl.conf'):
        shutil.copy2(package / name, runtime / name)
    for file in runtime.iterdir():
        if file.is_file(): file.chmod(0o644)
    secret_directory = root / 'external-sscl-secrets'
    print(run([sys.executable, package / 'configure_external_sscl.py', '--directory', secret_directory, '--client', args.client]).strip())
    django_uid = int(run(['docker', 'exec', 'dvadmin3-django', 'id', '-u']).strip())
    if django_uid != os.geteuid():
        os.chown(secret_directory / 'config.json', django_uid, -1)
    django_mounts = [bind(runtime / 'models.py', '/backend/pqkds/models.py'), bind(runtime / 'urls.py', '/backend/application/urls.py'),
                    bind(runtime / 'middleware.py', '/backend/dvadmin/utils/middleware.py'),
                    bind(runtime / 'external_sscl.py', '/backend/pqkds/external_sscl.py'), bind(runtime / 'external_sscl_views.py', '/backend/pqkds/external_sscl_views.py'),
                    bind(runtime / '0039_external_sscl_activation.py', '/backend/pqkds/migrations/0039_external_sscl_activation.py'),
                    bind(runtime / '0040_external_sm2_profile.py', '/backend/pqkds/migrations/0040_external_sm2_profile.py'),
                    bind(secret_directory / 'config.json', '/run/kms-external-sscl/config.json')]
    update = {'services': {
        'generate-java': {'volumes': [bind(runtime / 'kms-generate.jar', '/app/kms-generate.jar')]},
        'dvadmin3-django': {'environment': {'KMS_EXTERNAL_SSCL_ENABLED': 'true', 'KMS_EXTERNAL_SSCL_CONFIG': '/run/kms-external-sscl/config.json'}, 'volumes': django_mounts},
        'nginx': {'volumes': [bind(runtime / name, '/etc/nginx/' + ('snippets/' if name != 'nginx.conf' else '') + name) for name in ('nginx.conf', 'kms-demo-locations.conf', 'kms-external-sscl.conf')]},
    }}
    overlay.write_text(json.dumps(update, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    run(command + ['config', '--quiet'], cwd=root)
    run(command + ['run', '--rm', '--no-deps', '--entrypoint', '/docker-entrypoint.sh', 'nginx', 'nginx', '-t'], cwd=root)
    restart = command + ['up', '-d', '--no-deps', '--no-build', 'generate-java', 'dvadmin3-django', 'nginx']
    (root / 'start-external-sscl.sh').write_text('#!/bin/sh\nset -eu\ncd ' + shlex.quote(str(root)) + '\n' + shlex.join(restart) + '\n', encoding='utf-8')
    rollback = '#!/bin/sh\nset -eu\ncd ' + shlex.quote(str(root)) + '\n'
    if previous_overlay:
        rollback += 'cp ' + shlex.quote(str(backup / 'previous-overlay.json')) + ' ' + shlex.quote(str(overlay)) + '\n'
    rollback += shlex.join(original_command + ['up', '-d', '--no-deps', '--no-build', '--force-recreate', 'generate-java', 'dvadmin3-django', 'nginx']) + '\n'
    (backup / 'rollback.sh').write_text(rollback, encoding='utf-8')
    if args.activate:
        run(command + ['run', '--rm', '--no-deps', '--entrypoint', 'python', 'dvadmin3-django', 'manage.py', 'migrate', 'pqkds', '0040_external_sm2_profile', '--noinput'], cwd=root)
        print(run(restart + ['--force-recreate'], cwd=root).strip())
        print('已激活外部密钥接口，按节点名称默认生成SM2。安装过程未创建测试节点或提交测试链交易。')
    else:
        print('准备与配置校验完成；尚未执行数据库迁移或切换运行服务。加 --activate 可应用。')
    print('后续启动保留本覆盖文件：sh ' + str(root / 'start-external-sscl.sh'))
    print('回退脚本：' + str(backup / 'rollback.sh') + '（保留新增表/列和已生成材料）')


if __name__ == '__main__':
    try: main()
    except (OSError, ValueError, RuntimeError, KeyError, zipfile.BadZipFile) as exc:
        print('安装未完成：' + str(exc), file=sys.stderr)
        sys.exit(1)
