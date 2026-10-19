"""Build allowlisted software and private identity archives without printing credentials."""
import hashlib
import json
from pathlib import Path
import tarfile

RELEASE = Path(__file__).resolve().parent
PROJECT = RELEASE.parents[2]
MODULE = PROJECT / "kms-fabric-did"
RUNTIME = PROJECT / "kms-ops/fabric-did-secrets/syspid-yunId-channel4"


def main():
    private = RUNTIME / "deployment-channel4-20261019"
    private.mkdir(exist_ok=True)
    query = PROJECT / "output/did-parameters/channel4-confirmed-result-20261019.json"
    expected = json.loads(query.read_text(encoding="utf-8"))
    current = json.loads((RUNTIME / "verify-result.json").read_text(encoding="utf-8"))
    assert all(current[k] == expected[k] for k in ("txId", "did", "status", "transactionValid", "metadataMatches"))
    assert current["status"] == "CONFIRMED"
    network = json.loads((RUNTIME / "connection.json").read_text(encoding="utf-8"))
    assert network["channels"]["didchannel4"]["orderers"] == ["orderer-1-baas1"]
    with tarfile.open(RELEASE / "payload.tar.gz", "w:gz") as archive:
        archive.add(MODULE / "target/kms-fabric-did-1.0.0.jar", "module/target/kms-fabric-did-1.0.0.jar")
        for path in sorted((MODULE / "target/lib").glob("*.jar")):
            archive.add(path, "module/target/lib/" + path.name)
        for path in sorted((MODULE / "tools").glob("*.py")):
            archive.add(path, "module/tools/" + path.name)
        archive.add(MODULE / "target/test-classes", "offline-tests/classes")
        for source, name in ((Path.home() / ".m2/repository/junit/junit/4.13.2/junit-4.13.2.jar", "junit.jar"),
                             (Path.home() / ".m2/repository/org/hamcrest/hamcrest-core/1.3/hamcrest-core-1.3.jar", "hamcrest.jar")):
            archive.add(source, "offline-tests/" + name)
    identity = private / "identity.tar.gz"
    if not identity.exists():
        with tarfile.open(identity, "w:gz") as archive:
            for name in ("connection.json", "application-cert.pem", "application-key.pem", "controller-public.pem", "gm-sdk.properties"):
                archive.add(RUNTIME / name, name)
            archive.add(RUNTIME / "records", "records")
    # Public query identifiers only; no authentication material.
    (RELEASE / "query-parameters.json").write_bytes(query.read_bytes())
    files = [RELEASE / name for name in (
        "payload.tar.gz", "Dockerfile", ".dockerignore", "apply.sh", "check_deployment.py", "query_confirmed.py",
        "docker-compose.did-channel4.yml", "fabric.config.properties", "query-parameters.json", "DEPLOYMENT.md")]
    files.append(identity)
    manifest = "".join(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n" for path in files)
    (RELEASE / "SHA256SUMS").write_text(manifest, encoding="utf-8")
    print("RELEASE_BUILT software_files=" + str(len(files)) + " private_archive_in_restricted_runtime=true")


if __name__ == "__main__":
    main()
