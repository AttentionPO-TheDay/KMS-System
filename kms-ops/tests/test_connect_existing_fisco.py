import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

spec = importlib.util.spec_from_file_location(
    "connect_fisco", Path(__file__).resolve().parents[1] / "connect-existing-fisco.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
OWNER = "0x7e5f4552091a69125d5dfcb7b8c2659029395bdf"
CONTRACT = "0x" + "12" * 20


class ConnectExistingFiscoTests(unittest.TestCase):
    def test_pem_reader_and_owner_mismatch(self):
        key = ec.derive_private_key(1, ec.SECP256K1())
        pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
        valid = subprocess.run([sys.executable, "-c", module.KEY_READER, OWNER],
                               input=pem, capture_output=True)
        self.assertEqual(valid.returncode, 0)
        self.assertEqual(valid.stdout, b"0" * 63 + b"1")
        invalid = subprocess.run([sys.executable, "-c", module.KEY_READER, CONTRACT],
                                 input=pem, capture_output=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.assertEqual(invalid.stdout, b"")

    def test_env_deduplicates_and_preserves_unrelated_values(self):
        result = module.update_env("# comment\r\nA=old\r\nexport A=older\r\nOTHER=x\r\n",
                                   {"A": "new", "B": "added"})
        self.assertEqual(result, "# comment\nA=new\nOTHER=x\nB=added\n")

    def test_overlay_only_changes_java_and_contains_no_key(self):
        services = json.loads(module.overlay(CONTRACT))["services"]
        self.assertEqual(set(services), {"generate-java", "updatedel-java"})
        for service in services.values():
            self.assertEqual(service["environment"]["FABRIC_DID_ENABLED"], "false")
            self.assertTrue(service["environment"]["FISCO_PRIVATE_KEY"].startswith("${"))

    def test_real_deploy_script_including_separate_build_command(self):
        content = (Path(__file__).resolve().parents[1] / "deploy.sh").read_text(encoding="utf-8-sig")
        result = module.patch_deploy(content)
        self.assertEqual(result.count("-f docker-compose.fisco-enabled.yml"), 2)
        self.assertIn('docker compose -f "$COMPOSE_FILE" build', result)
        self.assertEqual(module.patch_deploy(result), result)

    def test_single_branch_wrapper(self):
        content = 'compose() {\n  docker compose -f "$COMPOSE_FILE" "$@"\n}\n'
        result = module.patch_deploy(content)
        self.assertEqual(result.count("-f docker-compose.fisco-enabled.yml"), 1)
        self.assertEqual(module.patch_deploy(result), result)

    def test_unknown_wrapper_rejected(self):
        with self.assertRaises(RuntimeError):
            module.patch_deploy("compose() {\n  something-else\n}\n")

    def fixture(self, root):
        (root / ".env").write_bytes(b"OTHER=preserve\r\nFISCO_PRIVATE_KEY=\r\n")
        (root / "docker-compose.yml").write_text("services: {}\n")
        (root / "deploy.sh").write_text('compose() {\n' +
                                       '  docker compose -f "$COMPOSE_FILE" "$@"\n' * 2 +
                                       '}\ndocker compose -f "$COMPOSE_FILE" build\n')
        directory = root / "fisco/console/account/ecdsa"
        directory.mkdir(parents=True)
        (directory / (OWNER + ".pem")).write_bytes(b"fixture")

    def exercise(self, fail_config=False, activate=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            original = (root / ".env").read_bytes()
            calls = []

            def fake_run(command, **kwargs):
                calls.append(command)
                if "./console.sh" in command:
                    return ("Return code: 0\nReturn values:(" + OWNER + ")").encode()
                if module.KEY_READER in command:
                    return b"0" * 63 + b"1"
                if "config" in command and fail_config:
                    raise RuntimeError("fixture validation failure")
                if "inspect" in command:
                    env = module.common_environment(CONTRACT, "0" * 63 + "1")
                    if command[-1] == "kms_updatedel_java":
                        env.update(KMS_LIFECYCLE_CHAIN_SYNC_ENABLED="true",
                                   KMS_LIFECYCLE_CHAIN_CONSUMER_ENABLED="true")
                    return json.dumps([k + "=" + v for k, v in env.items()]).encode()
                return b""

            old_cwd = Path.cwd()
            try:
                os.chdir(root)
                argv = ["script", "--contract", CONTRACT, "--owner", OWNER]
                if activate:
                    argv.append("--activate")
                with patch.object(sys, "argv", argv), patch.object(module, "run", fake_run), \
                        contextlib.redirect_stdout(io.StringIO()) as output:
                    if fail_config:
                        with self.assertRaises(RuntimeError):
                            module.main()
                    else:
                        module.main()
                        module.main()  # Idempotent deploy.sh patch.
                self.assertNotIn("0" * 63 + "1", output.getvalue())
                if fail_config:
                    self.assertEqual((root / ".env").read_bytes(), original)
                    self.assertFalse((root / "docker-compose.fisco-enabled.yml").exists())
                else:
                    self.assertEqual((root / "deploy.sh").read_text().count(
                        "-f docker-compose.fisco-enabled.yml"), 2)
                    self.assertIn("OTHER=preserve", (root / ".env").read_text())
                up_calls = [c for c in calls if "up" in c]
                self.assertEqual(bool(up_calls), activate)
                for command in up_calls:
                    self.assertIn("--no-deps", command)
                    self.assertEqual(command[-2:], ["generate-java", "updatedel-java"])
            finally:
                os.chdir(old_cwd)

    def test_configuration_without_restart(self):
        self.exercise()

    def test_invalid_compose_rolls_back(self):
        self.exercise(fail_config=True)

    def test_activation_scoped_to_java(self):
        self.exercise(activate=True)


if __name__ == "__main__":
    unittest.main()
