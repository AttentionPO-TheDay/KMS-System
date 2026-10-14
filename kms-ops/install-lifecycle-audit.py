"""Install acceptance-only persistent storage, preserving all other Compose settings."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
from datetime import datetime

VOLUME = "kms_acceptance_lifecycle"
TARGET = "/app/data/lifecycle-audit"


class InstallError(RuntimeError):
    """Safe diagnostic text, containing no subprocess output or configuration."""


def run(args, root):
    result = subprocess.run(args, cwd=root, capture_output=True, text=True)
    if result.returncode:
        raise InstallError("Docker command failed; inspect service status locally; output withheld to protect configuration")
    return result.stdout


def configure(config):
    changed = copy.deepcopy(config)
    service = changed["services"]["acceptance-backend"]
    volumes = service.setdefault("volumes", [])
    for item in volumes:
        parts = item.split(":") if isinstance(item, str) else None
        target = item.get("target") if isinstance(item, dict) else (parts[1] if len(parts) > 1 else parts[0])
        source = item.get("source") if isinstance(item, dict) else (parts[0] if len(parts) > 1 else None)
        if target == TARGET:
            if source != VOLUME:
                raise InstallError("Audit target is already mounted from a different source")
            if (isinstance(item, dict) and (item.get("read_only") or item.get("type", "volume") != "volume")) or (parts and len(parts) > 2 and "ro" in parts[2].split(",")):
                raise InstallError("Audit storage must be a writable named volume")
            break
    else:
        volumes.append(f"{VOLUME}:{TARGET}")
    declared = changed.setdefault("volumes", {})
    expected = {"name": VOLUME}
    if VOLUME in declared and declared[VOLUME] != expected:
        raise InstallError("Existing audit volume definition differs; refusing overwrite")
    declared[VOLUME] = expected
    return changed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    import yaml
    root = Path(__file__).resolve().parent
    base = root / "docker-compose.yml"
    original = base.read_bytes()
    config = yaml.safe_load(original)
    updated = configure(config)
    overlay = root / "docker-compose.fisco-enabled.yml"
    def compose(path):
        return ["docker", "compose", "-f", str(path)] + (["-f", str(overlay)] if overlay.exists() else []) + ["--profile", "fabric-did"]
    previous = json.loads(run(compose(base) + ["config", "--format", "json"], root))
    fd, temporary = tempfile.mkstemp(prefix=".audit-compose-", suffix=".yml", dir=root)
    os.close(fd)
    temp = Path(temporary)
    try:
        temp.write_text(yaml.safe_dump(updated, allow_unicode=True, sort_keys=False), encoding="utf-8")
        proposed = json.loads(run(compose(temp) + ["config", "--format", "json"], root))
        # Only the acceptance service mount and its volume definition may differ.
        for item in (previous, proposed):
            service = item["services"]["acceptance-backend"]
            service["volumes"] = [v for v in service.get("volumes", []) if v.get("target") != TARGET]
            item.setdefault("volumes", {}).pop(VOLUME, None)
        if previous != proposed:
            raise InstallError("Unexpected effective Compose changes; no config written")
        print("[OK] Only acceptance audit storage added; FISCO/TLS/environment/database settings unchanged")
        if not args.activate:
            print("[INFO] Read-only validation complete; use --activate after loading the new images")
            return
        if base.read_bytes() != original:
            raise InstallError("Compose changed concurrently; no config written")
        if updated != config:
            backup = root / ("lifecycle-compose-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".yml")
            backup.write_bytes(original)
            backup.chmod(0o600)
            temp.chmod(base.stat().st_mode & 0o777)
            os.replace(temp, base)
            print("[OK] Private Compose backup: " + backup.name)
        run(compose(base) + ["up", "-d", "--no-deps", "--force-recreate", "--no-build",
                            "updatedel-java", "acceptance-backend", "nginx"], root)
        print("[OK] Updated lifecycle Java, acceptance backend and gateway; no data cleared or key jobs replayed")
        print("[INFO] Open /acceptance/#/lifecycle and run new acceptance tests to record snapshots")
    finally:
        temp.unlink(missing_ok=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("[ERROR] " + (str(error) if isinstance(error, InstallError) else type(error).__name__ + ": lifecycle installation failed; do not send .env or private backups"))
        raise SystemExit(1)
