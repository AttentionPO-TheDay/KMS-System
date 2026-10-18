import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import sys_pid


class SysPidDiagnosticsTest(unittest.TestCase):
    def test_redacts_material_but_keeps_transport_error(self):
        raw = ('-----BEGIN PRIVATE KEY-----\nPRIVATE_DATA\n-----END PRIVATE KEY-----\n'
               'Authorization: Bearer AUTH_VALUE token=TOKEN_VALUE privateKey=KEY_VALUE '
               'connection error: PERMISSION_DENIED ENV_SECRET')
        safe = sys_pid.redact_log(raw, {"INTERNAL_TOKEN": "ENV_SECRET"})
        for secret in ("PRIVATE_DATA", "AUTH_VALUE", "TOKEN_VALUE", "KEY_VALUE", "ENV_SECRET"):
            self.assertNotIn(secret, safe)
        self.assertIn("PERMISSION_DENIED", safe)
        self.assertNotIn("AUTH_JSON_VALUE", sys_pid.redact_log('{"Authorization":"Bearer AUTH_JSON_VALUE"}', {}))
        self.assertNotIn("PARTIAL_KEY", sys_pid.redact_log("-----BEGIN PRIVATE KEY-----\nPARTIAL_KEY", {}))

    def test_read_only_run_has_backend_flags_and_isolated_logs(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            (runtime / "bridge.env.json").write_text('{"INTERNAL_TOKEN":"fixture-token"}', encoding="utf-8")
            arguments = ["sys_pid.py", "check", "--runtime", str(runtime), "--sys-pid-file", str(runtime / "pid.txt")]
            result = subprocess.CompletedProcess([], 0, b'{"status":"NOT_FOUND_OR_DEACTIVATED"}\n', b'WARN token=fixture-token')
            with patch.object(sys, "argv", arguments), patch.object(Path, "is_file", return_value=True), \
                    patch.object(sys_pid.subprocess, "run", return_value=result) as execute, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(0, sys_pid.main())
                first = json.loads(output.getvalue())
                output.seek(0)
                output.truncate(0)
                self.assertEqual(0, sys_pid.main())
                second = json.loads(output.getvalue())
            self.assertEqual(2, execute.call_count)  # 每次调用只启动一个 JVM，无隐式重试。
            env = execute.call_args.kwargs["env"]
            for flag in ("KMS_CHAIN_WRITES_ENABLED", "FABRIC_DID_WRITE_ENABLED", "FABRIC_DID_CREATE_POLICY_APPROVED"):
                self.assertEqual("false", env[flag])
            self.assertIn("-Dorg.slf4j.simpleLogger.defaultLogLevel=warn", execute.call_args.args[0])
            self.assertNotEqual(first["diagnostics"], second["diagnostics"])
            for report in (first, second):
                self.assertTrue((Path(report["diagnostics"]) / "result.json").is_file())
                self.assertNotIn("fixture-token", (Path(report["diagnostics"]) / "sdk.log").read_text(encoding="utf-8"))

    def test_timeout_keeps_logs_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime = Path(temporary)
            (runtime / "bridge.env.json").write_text('{}', encoding="utf-8")
            arguments = ["sys_pid.py", "verify", "--runtime", str(runtime), "--sys-pid-file", str(runtime / "pid.txt")]
            timeout = subprocess.TimeoutExpired("java", 90, output=b"partial log", stderr=b"TLS timeout")
            with patch.object(sys, "argv", arguments), patch.object(Path, "is_file", return_value=True), \
                    patch.object(sys_pid.subprocess, "run", side_effect=timeout) as execute, contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(2, sys_pid.main())
            execute.assert_called_once()
            report = json.loads(output.getvalue())
            self.assertEqual("SDK_TIMEOUT", report["errorCode"])
            self.assertIn("TLS timeout", (Path(report["diagnostics"]) / "sdk.log").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
