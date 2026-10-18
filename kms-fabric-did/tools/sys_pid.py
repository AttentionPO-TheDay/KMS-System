"""Run one supplier-chain operation in an isolated JVM; never change global service flags."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


def redact_log(text, env):
    """Only persisted diagnostics are exposed to operators; never echo raw SDK output."""
    text = re.sub(r"(?s)-----BEGIN ([A-Z0-9 ]+)-----.*?-----END \1-----", "[REDACTED PEM]", text)
    # A truncated process output may end in the middle of a PEM block.
    text = re.sub(r"(?s)-----BEGIN [A-Z0-9 ]+-----.*", "[REDACTED INCOMPLETE PEM]", text)
    text = re.sub(r"(?im)(authorization\s*[:=]\s*)(?:Bearer\s+|Basic\s+)?[^\s,;}]+", r"\1[REDACTED]", text)
    text = re.sub(
        r'''(?i)(["']?(?:private[_-]?key|secret|password|authorization|(?:[a-z0-9]+[_-])*token|casToken)["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;}&]+)''',
        r"\1[REDACTED]", text)
    for name, value in env.items():
        if value and any(word in name.upper() for word in ("TOKEN", "PASSWORD", "SECRET")):
            text = text.replace(value, "[REDACTED]")
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("onchain", "verify", "check", "preflight", "network-check", "retry"))
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--sys-pid-file", type=Path, required=True)
    parser.add_argument("--java", default="java")
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    module = Path(__file__).resolve().parents[1]
    jar = module / "target" / "kms-fabric-did-1.0.0.jar"
    if not jar.is_file():
        parser.error("Build kms-fabric-did first.")
    env = os.environ.copy()
    env.update(json.loads((runtime / "bridge.env.json").read_text(encoding="utf-8")))
    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    run = runtime / "diagnostics" / (started + "-" + args.operation + "-" + uuid.uuid4().hex[:8])
    run.mkdir(mode=0o700, parents=True)
    log_path = run / "sdk.log"
    exception_path = run / "exceptions.json"
    env["FABRIC_DID_DIAGNOSTICS_FILE"] = str(exception_path)
    # 仅这个显式 onchain 子进程放行写入；运行目录中保存的默认配置保持只读。
    for name in ("KMS_CHAIN_WRITES_ENABLED", "FABRIC_DID_WRITE_ENABLED", "FABRIC_DID_CREATE_POLICY_APPROVED"):
        env[name] = "true" if args.operation in ("onchain", "retry") else "false"
    classpath = os.pathsep.join((str(jar), str(module / "target" / "lib" / "*")))
    command = [args.java, "-Dfile.encoding=UTF-8", "-Dorg.slf4j.simpleLogger.defaultLogLevel=warn",
               "-Dorg.slf4j.simpleLogger.logFile=System.err",
               "-DfabricSDK.configuration=" + str(runtime / "gm-sdk.properties"),
               "-Dorg.hyperledger.fabric.sdk.configuration=" + str(runtime / "gm-sdk.properties"),
               "-cp", classpath, "com.kms.fabricdid.SysPidCommand", args.operation,
               str(args.sys_pid_file.resolve())]
    try:
        process = subprocess.run(command, cwd=runtime / "work", env=env, capture_output=True, timeout=90)
        output = process.stdout.decode("utf-8", errors="replace")
        errors = process.stderr.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode("utf-8", errors="replace")
        errors = (exc.stderr or b"").decode("utf-8", errors="replace")
        log_path.write_text(redact_log(output + "\n" + errors, env), encoding="utf-8")
        result = {"errorCode": "SDK_TIMEOUT", "action": "verify original transaction; do not delete records",
                  "diagnostics": str(run)}
        (run / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        return 2
    # SDK 日志只保存到受限运行目录，不把身份配置或长堆栈展开到终端。
    log_path.write_text(redact_log(output + "\n" + errors, env), encoding="utf-8")
    result = None
    for line in (output + "\n" + errors).splitlines():
        if not line.startswith("{"):
            continue
        try:
            candidate = json.loads(line)
        except ValueError:
            continue
        if isinstance(candidate, dict) and ("status" in candidate or "errorCode" in candidate):
            result = candidate
    if result is None:
        result = {"errorCode": "SDK_PROCESS_FAILED", "exitCode": process.returncode}
    result["diagnostics"] = str(run)
    (run / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    (runtime / (args.operation + "-result.json")).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    return process.returncode


if __name__ == "__main__":
    sys.exit(main())
