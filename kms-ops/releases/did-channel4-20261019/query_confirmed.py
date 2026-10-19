"""Query the confirmed SysPid via the private DID service; no ledger writes or token output."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parent


def command(*args):
    return subprocess.check_output(args, stderr=subprocess.PIPE)


def container(name="kms_fabric_did"):
    return json.loads(command("docker", "inspect", name))[0]


def environment(item):
    return dict(pair.split("=", 1) for pair in item["Config"]["Env"])


def request(item, path, body=None, authenticated=True):
    address = next(iter(item["NetworkSettings"]["Networks"].values()))["IPAddress"]
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["X-Internal-Token"] = environment(item)["INTERNAL_TOKEN"]
    req = urllib.request.Request("http://" + address + ":9094" + path,
                                 data=None if body is None else json.dumps(body).encode(), headers=headers)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=60) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def query(item=None):
    item = item or container()
    expected = json.loads((ROOT / "query-parameters.json").read_text(encoding="utf-8"))
    code, response = request(item, "/internal/fabric-did/sys-pids/verify", {"sysPid": expected["sysPid"]})
    if code != 200:
        raise RuntimeError("QUERY_HTTP_" + str(code) + "_" + str(response.get("data", {}).get("errorCode", "UNKNOWN")))
    result = response["data"]
    for key in ("provider", "chainId", "did", "sysPid", "txId", "status", "transactionValid", "metadataMatches"):
        if result.get(key) != expected[key]:
            raise RuntimeError("QUERY_MISMATCH_" + key)
    return {key: result[key] for key in ("did", "txId", "status", "transactionValid", "metadataMatches")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save", action="store_true", help="Save the non-secret result in the release directory")
    args = parser.parse_args()
    result = query()
    result["checkedAtUtc"] = datetime.now(timezone.utc).isoformat()
    if args.save:
        path = ROOT / "server-query-result.json"
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("DID_QUERY_FAILED " + (str(error) if isinstance(error, RuntimeError) else type(error).__name__), file=sys.stderr)
        sys.exit(1)
