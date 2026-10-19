"""只读发布检查；凭据只在内存使用，不打印环境、Compose 或身份材料。"""
import hashlib
import json
from pathlib import Path
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

RELEASE = Path(__file__).resolve().parent
COMPOSE = ["docker", "compose", "-p", "kms-ops", "-f", "/home/rbf/kms-sys/docker-compose.yml",
           "-f", "/home/rbf/kms-sys/docker-compose.fisco-enabled.yml", "--profile", "fabric-did"]
FLAGS = ("KMS_CHAIN_WRITES_ENABLED", "FABRIC_DID_WRITE_ENABLED", "FABRIC_DID_CREATE_POLICY_APPROVED", "FABRIC_DID_ENABLED")


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.PIPE)


def containers():
    ids = command("docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=kms-ops").decode().split()
    assert ids, "KMS project not found"
    return json.loads(command("docker", "inspect", *ids))


def environment(item):
    return dict(pair.split("=", 1) for pair in item["Config"]["Env"])


def other_services(items):
    return {c["Name"]: {"id": c["Id"], "startedAt": c["State"]["StartedAt"], "state": c["State"]["Status"]}
            for c in items if c["Name"] != "/kms_fabric_did"}


def request(opener, url, token=None, body=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Internal-Token"] = token
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), headers=headers)
    try:
        with opener.open(req, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main():
    items = containers()
    did = next(c for c in items if c["Name"] == "/kms_fabric_did")
    env = environment(did)
    assert all(env.get(flag) == "false" for flag in FLAGS), "DID is not fully disabled; stop for review"
    assert not did["HostConfig"]["PortBindings"], "DID port must remain private"
    if sys.argv[1] == "before":
        desired = json.loads(command(*COMPOSE, "config", "--format", "json"))["services"]["fabric-did-bridge"]
        assert desired["image"] == "kms-fabric-did:local"
        assert all(env.get(k) == str(v) for k, v in desired["environment"].items()), "Existing DID environment differs from Compose"
        assert all(str(desired["environment"].get(flag)) == "false" for flag in FLAGS)
        snapshot = {"did": did, "otherServices": other_services(items)}
        path = RELEASE / "backup" / "snapshot.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")
        path.chmod(0o600)
        print("PRECHECK_OK writes_disabled=true other_services=" + str(len(snapshot["otherServices"])))
        return
    before = json.loads((RELEASE / "backup" / "snapshot.json").read_text(encoding="utf-8"))
    assert other_services(items) == before["otherServices"], "Another KMS service changed during deployment"
    expected = command("docker", "image", "inspect", "kms-fabric-did:syspid-20261019", "--format", "{{.Id}}").decode().strip()
    assert did["Image"] == expected and did["Id"] != before["did"]["Id"]
    old_env = environment(before["did"])
    for key in old_env:
        if key not in ("PATH", "JAVA_HOME", "JAVA_VERSION", "ZULU_VERSION"):
            assert env.get(key) == old_env[key], "Unexpected environment change: " + key
    assert did["Mounts"] == before["did"]["Mounts"], "Identity mounts must not change"
    assert did["HostConfig"]["RestartPolicy"] == before["did"]["HostConfig"]["RestartPolicy"]
    actual = command("docker", "exec", "kms_fabric_did", "sha256sum", "/opt/kms-fabric-did/target/kms-fabric-did-1.0.0.jar").decode().split()[0]
    assert actual == hashlib.sha256((RELEASE / "payload/module/target/kms-fabric-did-1.0.0.jar").read_bytes()).hexdigest()
    address = next(iter(did["NetworkSettings"]["Networks"].values()))["IPAddress"]
    base = "http://" + address + ":9094"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for attempt in range(20):
        try:
            code, raw = request(opener, base + "/health")
            if code == 200:
                break
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(1)
    else:
        raise AssertionError("DID readiness timeout")
    assert json.loads(raw)["data"]["writeEnabled"] is False
    token = env["INTERNAL_TOKEN"]
    for action, error in (("onchain", "CHAIN_WRITES_PAUSED"), ("verify", "DISABLED")):
        # 禁写断言已通过；请求只验证新路由及闸门，不会初始化 SDK、生成密钥或提交交易。
        code, raw = request(opener, base + "/internal/fabric-did/sys-pids/" + action, token, {"sysPid": "00"})
        assert code == 503 and json.loads(raw)["data"]["errorCode"] == error, "SysPid route gate failed"
    assert request(opener, base + "/internal/fabric-did/sys-pids/verify", body={"sysPid": "00"})[0] == 401
    cert = command("docker", "exec", "kms_gateway", "cat", "/run/kms-server-tls/server.crt").decode()
    tls = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ssl.create_default_context(cadata=cert)))
    for path in ("/ping", "/updatedel/demo", "/acceptance/"):
        assert request(tls, "https://10.112.125.22:8443" + path)[0] == 200
    print("DEPLOY_OK jar_hash_matches=true syspid_routes=true auth_gate=true writes_disabled=true tls_pages=200 other_services_unchanged=true")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("DEPLOY_CHECK_FAILED type=" + type(error).__name__, file=sys.stderr)
        sys.exit(1)
