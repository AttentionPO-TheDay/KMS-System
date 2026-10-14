#!/usr/bin/env python3
"""Expose only the KMS gateway on a specific server IPv4 address with TLS.

Requires connect-existing-fisco.py alongside this file; run from kms-sys.
"""
import argparse
from datetime import datetime
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import traceback

spec = importlib.util.spec_from_file_location(
    "fisco_helpers", Path(__file__).with_name("connect-existing-fisco.py"))
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

CLIENT_SERVICES = ("generate-java", "updatedel-java", "dvadmin3-django", "acceptance-backend")


def server_template(original, address):
    marker = "# BEGIN KMS SERVER ACCESS"
    original = re.sub(r"(?ms)^# BEGIN KMS SERVER ACCESS\n.*?^# END KMS SERVER ACCESS\n?", "", original)
    if marker in original:
        raise RuntimeError("Malformed existing server template marker")
    # IP clients commonly omit SNI. TLS certificate selection happens before
    # the HTTP Host header, so the IP certificate must be the 443 default.
    original = re.sub(r"(?m)^(\s*listen\s+443\s+ssl)\s+default_server(\s*;)",
                      r"\1\2", original)
    return original.rstrip() + "\n" + f'''{marker}
server {{
    listen 80;
    listen 8088;
    server_name {address};
    return 308 https://{address}:8443$request_uri;
}}
server {{
    listen 443 ssl default_server;
    server_name {address};
    ssl_certificate /run/kms-server-tls/server.crt;
    ssl_certificate_key /run/kms-server-tls/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    include /etc/nginx/snippets/kms-security-headers.conf;
    client_max_body_size 20m;
    include /etc/nginx/snippets/kms-demo-locations.conf;
}}
# END KMS SERVER ACCESS
'''


def configure(compose, address):
    services = compose["services"]
    gateway = services["nginx"]
    ports = gateway.setdefault("ports", [])
    for published, target in ((80, 80), (8088, 8088), (8443, 443)):
        if not any(p.get("host_ip") == address and str(p["published"]) == str(published)
                   and int(p["target"]) == target for p in ports):
            ports.append({"host_ip": address, "published": str(published),
                          "target": target, "protocol": "tcp"})
    volumes = gateway.setdefault("volumes", [])
    targets = {"/etc/nginx/kms-demo.template", "/run/kms-server-tls"}
    volumes[:] = [v for v in volumes if v.get("target") not in targets]
    volumes.extend([
        {"type": "bind", "source": "./server-access/kms-demo.template",
         "target": "/etc/nginx/kms-demo.template", "read_only": True},
        {"type": "bind", "source": "./server-access/tls",
         "target": "/run/kms-server-tls", "read_only": True},
    ])
    hosts = ",".join([address] + [f"{address}:{p}" for p in (80, 8088, 8443)])
    origins = ",".join([f"http://{address}", f"http://{address}:80",
                         f"http://{address}:8088", f"https://{address}:8443"])
    for name in CLIENT_SERVICES:
        env = services[name].get("environment") or {}
        # --no-interpolate can preserve Compose's KEY=value list syntax.
        # Convert it without expanding variables or losing '=' in values.
        if isinstance(env, list):
            mapping = {}
            for item in env:
                if not isinstance(item, str):
                    raise RuntimeError(name + ": unsupported environment entry type")
                key, separator, value = item.partition("=")
                mapping[key] = value if separator else None
            env = mapping
        if not isinstance(env, dict):
            raise RuntimeError(name + ": unsupported environment format")
        services[name]["environment"] = env
        for key, additions in (("KMS_DEMO_ALLOWED_HOSTS", hosts),
                               ("KMS_DEMO_ALLOWED_ORIGINS", origins)):
            existing = env.get(key) or ("127.0.0.1,localhost,127.0.0.1:8088,localhost:8088"
                                       if key.endswith("HOSTS") else
                                       "http://127.0.0.1:8088,http://localhost:8088")
            # Preserve the original .env interpolation, never expand secrets.
            suffix = "," + additions
            env[key] = existing if suffix in existing else existing + suffix
    return compose


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    address = str(ipaddress.IPv4Address(args.ip))
    root = Path.cwd()
    base = root / "docker-compose.yml"
    if not base.is_file() or base.is_symlink() or not (root / ".env").is_file():
        raise RuntimeError("Run from the server deployment directory")
    interfaces = json.loads(helpers.run(["ip", "-j", "-4", "addr", "show"]))
    if address not in {a.get("local") for i in interfaces for a in i.get("addr_info", [])}:
        raise RuntimeError("The requested IP is not assigned to this server")
    compose = ["docker", "compose", "-f", "docker-compose.yml"]
    profile = ["--profile", "fabric-did"] if (root / "WITH_DID").exists() else []
    config = json.loads(helpers.run(compose + profile + ["config", "--no-interpolate",
                           "--no-path-resolution", "--format", "json"]))
    original = helpers.run(["docker", "exec", "kms_gateway", "cat",
                            "/etc/nginx/kms-demo.template"]).decode("utf-8")
    previous_environments = {name: json.dumps(config["services"][name].get("environment"),
                                              sort_keys=True) for name in CLIENT_SERVICES}
    config = configure(config, address)
    changed_clients = [name for name in CLIENT_SERVICES if json.dumps(
        config["services"][name].get("environment"), sort_keys=True) != previous_environments[name]]
    directory = root / "server-access"
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    tls = directory / "tls"
    tls.mkdir(mode=0o700, exist_ok=True)
    cert, key = tls / "server.crt", tls / "server.key"
    if not cert.exists() and not key.exists():
        old_umask = os.umask(0o077)
        try:
            helpers.run(["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
                         "-days", "365", "-keyout", str(key), "-out", str(cert),
                         "-subj", "/CN=" + address,
                         "-addext", "subjectAltName=IP:" + address,
                         "-addext", "basicConstraints=critical,CA:FALSE"])
        finally:
            os.umask(old_umask)
    if not cert.is_file() or not key.is_file():
        raise RuntimeError("Incomplete TLS files; neither file was overwritten")
    san = helpers.run(["openssl", "x509", "-in", str(cert), "-noout", "-ext", "subjectAltName"])
    if "IP Address:" + address not in san.decode():
        raise RuntimeError("Existing certificate does not cover the requested IP")
    os.chmod(key, 0o600)
    original_base = base.read_bytes()
    template = directory / "kms-demo.template"
    old_template = template.read_bytes() if template.exists() else None
    backup = root / ("server-access-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    backup.mkdir(mode=0o700)
    helpers.atomic_write(backup / base.name, original_base)
    if old_template is not None:
        helpers.atomic_write(backup / template.name, old_template)
    effective = compose + (["-f", "docker-compose.fisco-enabled.yml"]
                           if (root / "docker-compose.fisco-enabled.yml").exists() else []) + profile
    try:
        helpers.atomic_write(template, server_template(original, address).encode())
        helpers.atomic_write(base, (json.dumps(config, indent=2) + "\n").encode())
        helpers.run(effective + ["config", "--quiet"])
        helpers.run(effective + ["run", "--rm", "--no-deps", "nginx", "nginx", "-t"])
    except Exception:
        helpers.atomic_write(base, original_base)
        if old_template is None:
            template.unlink(missing_ok=True)
        else:
            helpers.atomic_write(template, old_template)
        raise
    print("[OK] Gateway bindings, Host/Origin lists and nginx syntax validated")
    print("[OK] FISCO overlay and non-gateway port bindings preserved")
    print("[OK] Config backup: " + backup.name)
    if args.activate:
        helpers.run(effective + ["up", "-d", "--no-deps", "--no-build", "--force-recreate",
                                 *changed_clients, "nginx"])
        helpers.run(["docker", "exec", "kms_gateway", "nginx", "-t"])
        published = json.loads(helpers.run(["docker", "inspect", "--format",
                                            "{{json .NetworkSettings.Ports}}", "kms_gateway"]))
        for host_port, container_port in ((80, 80), (8088, 8088), (8443, 443)):
            bindings = published.get(str(container_port) + "/tcp") or []
            if not any(p.get("HostIp") == address and p.get("HostPort") == str(host_port)
                       for p in bindings):
                raise RuntimeError("Running gateway port bindings do not match requested IP")
        helpers.run(["curl", "-q", "--noproxy", "*", "--cacert", str(cert), "--fail", "--silent",
                     "--show-error", "--max-time", "15", "--retry", "3", "--retry-connrefused",
                     "--retry-delay", "1", "--retry-max-time", "20",
                     "https://" + address + ":8443/ping"])
        print("[OK] Gateway and changed whitelist services recreated")
        print("[OK] Running port bindings and certificate-verified HTTPS /ping checked")
    print("[INFO] URL: https://" + address + ":8443/updatedel/")
    helpers.atomic_write(root / "kms-server.crt", cert.read_bytes(), 0o644)
    print("[INFO] Trust kms-server.crt on clients after verifying fingerprint")
    fingerprint = helpers.run(["openssl", "x509", "-in", str(cert), "-noout", "-fingerprint", "-sha256"])
    print(fingerprint.decode().strip())
    print("[INFO] Never copy server.key, .env or backup directories to clients")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("[ERROR] " + (str(error) if isinstance(error, RuntimeError) else
                            type(error).__name__ + ": operation failed; details withheld"))
        for frame in traceback.extract_tb(error.__traceback__)[-4:]:
            # Code location only: no source lines, exception payload or locals.
            print("[AT] " + Path(frame.filename).name + ":" + str(frame.lineno) +
                  " in " + frame.name)
        raise SystemExit(1)
