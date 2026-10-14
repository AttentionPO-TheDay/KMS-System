#!/usr/bin/env python3
"""Connect the server image bundle to an existing KeyEvidence contract.

Run on the server, from kms-sys. Never deploys a contract or alters chain data.
Host needs Python 3; key parsing uses the already-running Django container.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime


KEY_READER = r'''
import sys
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from Crypto.Hash import keccak
try:
    key = serialization.load_pem_private_key(sys.stdin.buffer.read(), password=None)
    if not isinstance(key, ec.EllipticCurvePrivateKey) or key.curve.name != "secp256k1":
        raise ValueError("Expected ECDSA secp256k1")
    pub = key.public_key().public_bytes(serialization.Encoding.X962,
                                       serialization.PublicFormat.UncompressedPoint)
    h = keccak.new(digest_bits=256)
    h.update(pub[1:])
    address = "0x" + h.hexdigest()[-40:]
    if address.lower() != sys.argv[1].lower():
        raise ValueError("PEM address does not match contract owner")
    sys.stdout.write(format(key.private_numbers().private_value, "064x"))
except Exception:
    sys.stderr.write("Account parsing or owner validation failed\n")
    sys.exit(1)
'''


def run(command, **kwargs):
    # Captured output can contain secrets. Never include it in error messages.
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=120, **kwargs)
    if result.returncode:
        raise RuntimeError("Command failed: " + " ".join(command[:3]) +
                           " (output withheld to protect credentials)")
    return result.stdout


def update_env(content, values):
    lines = content.replace("\r\n", "\n").splitlines()
    remaining = dict(values)
    output = []
    for line in lines:
        match = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        key = match.group(1) if match else None
        if key in values:
            if key in remaining:
                output.append(key + "=" + remaining.pop(key))
        else:
            output.append(line)
    output.extend(key + "=" + value for key, value in remaining.items())
    return "\n".join(output) + "\n"


def patch_deploy(content):
    # The build command elsewhere also uses COMPOSE_FILE. Only patch the wrapper.
    content = content.replace("\r\n", "\n")
    function = re.search(r"(?ms)^compose\(\)\s*\{\n(?P<body>.*?)^\}", content)
    if not function:
        raise RuntimeError("compose() wrapper not found; no config changed")
    body = function.group("body")
    base = 'docker compose -f "$COMPOSE_FILE"'
    patched = base + ' -f docker-compose.fisco-enabled.yml'
    # Accept one or more branches, and allow safe repeated execution.
    count = body.count(base)
    if not count or body.count("docker-compose.fisco-enabled.yml") != body.count(patched):
        raise RuntimeError("Unexpected compose() layout; no config changed")
    body = body.replace(patched, base).replace(base, patched)
    return content[:function.start("body")] + body + content[function.end("body"):]


def atomic_write(path, data, mode=0o600):
    fd, name = tempfile.mkstemp(prefix=".fisco-config-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def overlay(contract):
    common = {
        "KMS_CHAIN_BACKEND": "legacy",
        "KMS_CHAIN_WRITES_ENABLED": "true",
        "KMS_CHAIN_CONSUMER_ENABLED": "true",
        "FISCO_HOST": "fisco-node",
        "FISCO_CONTRACT_ADDRESS": contract,
        "FISCO_PRIVATE_KEY": "${FISCO_PRIVATE_KEY:?FISCO_PRIVATE_KEY is required}",
        "FABRIC_DID_ENABLED": "false",
        "FABRIC_DID_WRITE_ENABLED": "false",
    }
    lifecycle = dict(common, KMS_LIFECYCLE_CHAIN_SYNC_ENABLED="true",
                     KMS_LIFECYCLE_CHAIN_CONSUMER_ENABLED="true")
    # JSON is also valid YAML, avoiding a new host dependency on PyYAML.
    return json.dumps({"services": {
        "generate-java": {"environment": common},
        "updatedel-java": {"environment": lifecycle},
    }}, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--activate", action="store_true",
                        help="Recreate only the two Java services; may process queued tasks")
    args = parser.parse_args()
    if not all(re.fullmatch(r"0x[0-9a-fA-F]{40}", v) for v in (args.contract, args.owner)):
        raise RuntimeError("Contract and owner must be 20-byte hex addresses")
    root = Path.cwd()
    env_path, deploy_path = root / ".env", root / "deploy.sh"
    overlay_path = root / "docker-compose.fisco-enabled.yml"
    for path in (env_path, deploy_path, root / "docker-compose.yml"):
        if not path.is_file() or path.is_symlink():
            raise RuntimeError("Run from the deployment directory; missing/unsafe " + path.name)
    pem = root / "fisco/console/account/ecdsa" / (args.owner.lower() + ".pem")
    if not pem.is_file():
        raise RuntimeError("The specified owner PEM is missing")
    owner_output = run(["docker", "exec", "-w", "/app", "kms_fisco_console",
                        "bash", "./console.sh", "call", "KeyEvidence", args.contract, "owner"])
    owner_text = owner_output.decode("utf-8", errors="replace")
    found = re.search(r"Return values:\s*\(\s*(0x[0-9a-fA-F]{40})\s*\)", owner_text)
    if not found or found.group(1).lower() != args.owner.lower() or not re.search(
            r"Return code:\s*0\b", owner_text):
        raise RuntimeError("Live contract owner verification failed; no config changed")
    private = run(["docker", "exec", "-i", "dvadmin3-django", "python", "-c",
                   KEY_READER, args.owner], input=pem.read_bytes()).decode("ascii")
    if not re.fullmatch(r"[0-9a-f]{64}", private):
        raise RuntimeError("Invalid account scalar; no config changed")
    print("[OK] Live owner and PEM-derived address match: " + args.owner)
    deploy = patch_deploy(deploy_path.read_text(encoding="utf-8-sig"))
    values = {"FISCO_CONTRACT_ADDRESS": args.contract, "FISCO_PRIVATE_KEY": private,
              "KMS_CHAIN_BACKEND": "legacy", "FABRIC_DID_ENABLED": "false",
              "FABRIC_DID_WRITE_ENABLED": "false"}
    files = {env_path: update_env(env_path.read_text(encoding="utf-8-sig"), values).encode(),
             deploy_path: deploy.encode(), overlay_path: overlay(args.contract).encode()}
    originals = {path: (path.read_bytes() if path.exists() else None) for path in files}
    backup = root / ("fisco-config-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(mode=0o700)
    for path, data in originals.items():
        if data is not None:
            atomic_write(backup / path.name, data)
    compose = ["docker", "compose", "-f", "docker-compose.yml", "-f", overlay_path.name]
    if (root / "WITH_DID").exists():
        compose += ["--profile", "fabric-did"]
    try:
        for path, data in files.items():
            atomic_write(path, data, 0o700 if path == deploy_path else 0o600)
        run(["bash", "-n", str(deploy_path)])
        run(compose + ["config", "--quiet"])
    except Exception:
        for path, data in originals.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, data, 0o700 if path == deploy_path else 0o600)
        raise
    print("[OK] Config validated; private key stored without printing it")
    print("[OK] Private config backup: " + backup.name)
    print("[OK] Only Java FISCO writes enabled; Django/Web3 and DID remain paused")
    if args.activate:
        print("[INFO] Activating Java consumers; queued evidence tasks may now execute", flush=True)
        run(compose + ["up", "-d", "--no-deps", "--force-recreate", "--no-build",
                       "generate-java", "updatedel-java"])
        for name in ("kms_generate_java", "kms_updatedel_java"):
            env = json.loads(run(["docker", "inspect", "--format", "{{json .Config.Env}}", name]))
            actual = dict(item.split("=", 1) for item in env if "=" in item)
            expected = common_environment(args.contract, private)
            if name == "kms_updatedel_java":
                expected.update(KMS_LIFECYCLE_CHAIN_SYNC_ENABLED="true",
                                KMS_LIFECYCLE_CHAIN_CONSUMER_ENABLED="true")
            if any(actual.get(key) != value for key, value in expected.items()):
                raise RuntimeError(name + ": running configuration mismatch")
            print("[OK] " + name + ": contract/account/write switches match")
        print("[INFO] Container config checked; business transaction receipt still needs verification")
    else:
        print("[INFO] No containers restarted. Re-run with --activate when ready.")


def common_environment(contract, private):
    return {"KMS_CHAIN_BACKEND": "legacy", "KMS_CHAIN_WRITES_ENABLED": "true",
            "KMS_CHAIN_CONSUMER_ENABLED": "true", "FISCO_CONTRACT_ADDRESS": contract,
            "FISCO_PRIVATE_KEY": private, "FISCO_HOST": "fisco-node",
            "FABRIC_DID_ENABLED": "false", "FABRIC_DID_WRITE_ENABLED": "false"}


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never emit traceback, subprocess output or config contents.
        print("[ERROR] " + (str(error) if isinstance(error, RuntimeError)
                            else type(error).__name__ + ": operation failed; details withheld"))
        raise SystemExit(1)
