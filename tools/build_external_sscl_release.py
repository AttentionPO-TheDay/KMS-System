#!/usr/bin/env python3
"""Build the external SM2 increment, retaining the legacy SSCL implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=root / 'output' / 'external-sm2-activation-20261022-r2')
    args = parser.parse_args()
    destination = args.output.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    backend = root / 'kms-distribute/dvadmin/backend'
    classes = root / 'kms-generate/java-backend'
    files = {
        'external_sscl.py': backend / 'pqkds/external_sscl.py',
        'external_sscl_views.py': backend / 'pqkds/external_sscl_views.py',
        '0039_external_sscl_activation.py': backend / 'pqkds/migrations/0039_external_sscl_activation.py',
        '0040_external_sm2_profile.py': backend / 'pqkds/migrations/0040_external_sm2_profile.py',
        'InternalSsclController.class': classes / 'ruoyi-admin/target/classes/com/ruoyi/generate/controller/InternalSsclController.class',
        'SSCLGenerator.class': classes / 'ruoyi-system/target/classes/com/ruoyi/generate/service/generator/SSCLGenerator.class',
        'kms-external-sscl.conf': root / 'kms-ops/nginx/snippets/kms-external-sscl.conf',
        'install.py': root / 'tools/install_external_sscl.py',
        'configure_external_sscl.py': root / 'tools/configure_external_sscl.py',
        'external_sscl_client.py': root / 'output/external_sscl_client.py',
        'query_sm2_by_syspid.py': root / 'output/query_sm2_by_syspid.py',
        'API.md': root / 'output/DID外部平台SM2接口-192.168.129.34.md',
    }
    for name, source in files.items():
        if name.endswith('.class') and int.from_bytes(source.read_bytes()[6:8], 'big') != 52:
            raise RuntimeError('Java class must target Java 8: ' + name)
        shutil.copy2(source, destination / name)
    models = (backend / 'pqkds/models.py').read_text(encoding='utf-8')
    block = models[models.index('class ExternalNodeActivation(models.Model):'):models.index('class NodeKeyDidRecord(models.Model):')]
    (destination / 'model-block.txt').write_text(block, encoding='utf-8')
    (destination / 'node-profile.txt').write_text(next(line for line in models.splitlines(True) if 'initialization_profile = models.CharField' in line), encoding='utf-8')
    audit = (backend / 'dvadmin/utils/middleware.py').read_text(encoding='utf-8')
    start = audit.index("    if path.rstrip('/') == '/external-api/v1/nodes/activate':")
    end = audit.index("    if '/node-self/keygen/' not in path", start)
    (destination / 'audit-block.txt').write_text(audit[start:end], encoding='utf-8')
    (destination / 'README.md').write_text('''# 外部平台 SM2 协议密钥增量包

日期：2026-10-22。按节点名称默认生成并登记标准 SM2 公私钥（sm2p256v1，P=dG），取得新的 SysPid。保留原私钥领取、登记状态、DID 状态及平台令牌认证，不需要 Demo 会话。

接口沿用 `/external-api/v1/nodes/activate/`。激活 POST `{"nodeName":"demo-ts","algorithm":"SM2","includePrivateKey":true}`。SM2 使用固定标准基点，不需要 SSCL 的 domainPublicKey。已有 SSCL 记录保持原密钥和 SysPid；相同名称首次申请 SM2 创建独立的 SM2 记录。按 SysPid 查询返回原算法，可显式传 algorithm=SM2 校验。

私钥领取 POST `{"sysPid":"<完整值>","algorithm":"SM2","includePrivateKey":true}`。GET 不返回私钥。已撤销密钥、停用节点及其他平台的请求被拒绝。原私钥仍加密保存；SysPid 查询/领取不生成新密钥、不分配新标识、不重新提交交易。此包可直接从原自动激活包升级。

适用于已安装 2026-10-20 节点生成页 DID 补充包的 Linux 服务器，要求迁移 0038 已应用、DID Bridge 已配置且节点密钥 DID 流程已启用。不是完整数据库或完整镜像包。

## 部署

将本目录上传并解压到服务器，在目录内执行（部署根目录以实际路径为准）：

```bash
sudo python3 install.py --root /home/vm103/Project2/opt/kms/kms-server --client partner-a --activate
```

保留已有令牌、加密配置、节点、公钥和 SysPid。迁移 0040 仅增加 EXTERNAL_SM2 初始化选项，不转换原 SSCL 数据。脚本文件名 external_sscl_client.py、虚拟环境 .venv-sscl、原配置和挂载名沿用以便升级，默认算法已改为 SM2。

安装完成后，更新调用方目录的脚本和文档（不需要替换原令牌和证书）：

```bash
sudo install -o vm103 -m 644 external_sscl_client.py query_sm2_by_syspid.py API.md "/home/vm103/Identity Authentication/"
```

调用方进入当前目录后执行：

```bash
cd "/home/vm103/Identity Authentication"
.venv-sscl/bin/python external_sscl_client.py --node-name 'demo-ts' --algorithm SM2 --token-file ./partner-a.token --ca ./kms-server.crt --output ./sm2-activation-result.json --private-key-output ./sm2-private-key.json
```

把 --node-name 换成 --sys-pid 'SM2返回的完整SysPid' 可领取已有 SM2 私钥。私钥 JSON 保存私钥、标准公钥、算法、曲线和 SysPid，Linux 权限 600；终端和普通 JSON 不包含私钥。各节点用独立的私钥文件名。仅更新客户端不能让旧服务端生成 SM2，完整调用见 API.md。

专用查询脚本可单独交付，只依赖 requests。令牌和证书默认从脚本所在目录读取，使用现有文件即可：

```bash
cd "/home/vm103/Identity Authentication"
.venv-sscl/bin/python query_sm2_by_syspid.py --sys-pid 'SM2返回的完整SysPid' --output ./sm2-status.json
```

脚本只发送 GET，返回公钥、登记状态和 DID 状态。默认校验 SM2；历史 SSCL 查询需传 --algorithm SSCL。已安装上一版 SM2 包时，只需复制新增查询脚本与 API.md，无需重新安装服务端。

安装器保留当前 Compose 文件列表、已有覆盖文件，备份原 JAR、相关配置和前一版覆盖文件，应用迁移到 0040，只重建 generate-java、dvadmin3-django 和 nginx。不修改 .env、链地址/通道、写入开关，不在安装中创建业务节点或发送上链请求。SM2 复用平台标准曲线实现，不调用 SSCL 份额生成器；SSCL 的两个 Java 类保持原版本以支持历史协议。

不传 --activate 时只准备补丁、接入配置和校验网关，暂不迁移/切换服务。更换 client 可增加其他接入平台；已有平台保留原令牌。重复安装保留私钥加密配置和历史材料。

SM2 外部节点的配置为 EXTERNAL_SM2，只初始化 SM2；旧 EXTERNAL_SSCL 与 FULL 节点保留原配置和材料。

## 交给调用方

- external_sscl_client.py、query_sm2_by_syspid.py、API.md。
- 部署目录 external-sscl-secrets/partner-a.token：只交给该平台。
- 服务器公开的 kms-server.crt。

config.json 内含私钥加密主密钥，应留在服务器并备份。不能重新生成它来处理旧节点解密失败。

## 启动与回退

后续使用部署目录生成的 start-external-sscl.sh，保留原 Compose 文件和新增覆盖文件。仅使用原启动命令重新创建容器会丢失新接口的代码挂载。

安装器输出备份目录内 rollback.sh，可恢复原服务配置；回退保留新增数据表、兼容列和已生成密钥材料，不做逆向迁移。

验证记录见 VALIDATION.md。未连接 192.168.129.34 提交真实 DID 交易。详细调用协议见 API.md。
''', encoding='utf-8')
    (destination / 'VALIDATION.md').write_text('''# 本地验证记录（2026-10-22）

- r2 新增专用 SysPid 查询脚本：8 项在 Windows、Linux 均通过；检查 GET 查询、TLS、脚本目录凭据路径、SysPid/算法/曲线匹配、错误/待确认状态和私钥字段过滤。原调用脚本 13 项 Linux 回归通过。服务端及安装器与前版 SM2 包逐字节一致，下列服务端验证沿用前版结果。
- 新接口 Python：41 项通过；验证 SM2 标准基点已知向量、公私钥加解密、默认 SM2、算法隔离、旧 SSCL 原值兼容、幂等/重试/跨平台隔离、私钥加密/匹配校验、登记状态及 DID 原交易核验。
- 客户端：13 项，Linux 全部通过；验证默认 SM2、响应算法/曲线匹配、历史 SysPid 如实返回、私钥单独保存和 600 权限/链接拒绝。Windows 跳过一个 POSIX 权限测试。
- 原节点密钥 DID 回归：8 项通过。
- Java、网关配置沿用已验证原版本，本次不修改。原 Java 11 项及真实 SSCL 跨语言互通记录属于原包基线验证。
- 临时 MySQL 8：2 项通过；实际执行迁移 0039/0040，旧 FULL、EXTERNAL_SSCL 节点保持原值；SM2、SSCL 分别执行 8 个并发首次请求加 8 个重试，各仅一把密钥、一个 SysPid、一次提交。检查原私钥导出及大小写不敏感排序规则下的平台隔离。
- 网关配置沿用原包；原包基线已通过隔离 Nginx 入口脚本、nginx -t 和 Compose 校验。本次安装器仍会在服务器切换前执行 nginx -t 和 Compose 校验。
- 安装器：检查原 Node 初始化配置可升级并重复应用幂等，模型和迁移状态一致；原接入配置、令牌、加密主密钥保留。

测试没有加载生产 Django 配置、没有连接现有数据库、没有使用真实 DID Bridge。MySQL 测试新建的容器和网络在结束后清理。

原自动激活包已由用户安装。本 SM2 修订尚未在 192.168.129.34 安装或在线核验；安装与实际链状态以服务器结果为准。
''', encoding='utf-8')
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in destination.iterdir() if path.is_file() and path.name != 'manifest.json'}
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    archive = destination.with_suffix('.tar.gz')
    with tarfile.open(archive, 'w:gz') as stream:
        for path in sorted(destination.iterdir()):
            if path.is_file(): stream.add(path, arcname=destination.name + '/' + path.name)
    print(archive)
    print('SHA256 ' + hashlib.sha256(archive.read_bytes()).hexdigest())


if __name__ == '__main__': main()
