import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import unittest

spec = importlib.util.spec_from_file_location(
    "expose_server", Path(__file__).resolve().parents[1] / "expose-server.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
ADDRESS = "10.112.125.22"


class ExposeServerTests(unittest.TestCase):
    def fixture(self):
        services = {name: {"environment": {
            "KMS_CHAIN_WRITES_ENABLED": "false",
            "FABRIC_DID_ENABLED": "false",
            "KMS_DEMO_ALLOWED_HOSTS": "${KMS_DEMO_ALLOWED_HOSTS:-localhost:8088}",
            "KMS_DEMO_ALLOWED_ORIGINS": "${KMS_DEMO_ALLOWED_ORIGINS:-http://localhost:8088}",
        }} for name in module.CLIENT_SERVICES}
        services["nginx"] = {"ports": [{"host_ip": "127.0.0.1", "target": 80,
                                         "published": "80"}],
                              "volumes": [{"type": "bind", "source": "./nginx/logs",
                                           "target": "/var/log/nginx"}]}
        services["mysql"] = {"ports": [{"host_ip": "127.0.0.1", "published": "3307",
                                         "target": 3306}]}
        services["fisco-node0"] = {"networks": {"kms_net": {"ipv4_address": "172.24.0.10"}}}
        return {"services": services, "networks": {"kms_net": {"ipam": {
            "config": [{"subnet": "172.24.0.0/16"}]}}}}

    def test_ports_only_gateway_and_preserve_network(self):
        fixture = self.fixture()
        original = copy.deepcopy(fixture)
        result = module.configure(fixture, ADDRESS)
        for name in ("mysql", "fisco-node0"):
            self.assertEqual(result["services"][name], original["services"][name])
        self.assertEqual(result["networks"], original["networks"])
        ports = result["services"]["nginx"]["ports"]
        self.assertEqual({(p["host_ip"], p["published"]) for p in ports},
                         {("127.0.0.1", "80"), (ADDRESS, "80"),
                          (ADDRESS, "8088"), (ADDRESS, "8443")})

    def test_whitelists_preserve_interpolation_and_chain_switches(self):
        result = module.configure(self.fixture(), ADDRESS)
        for name in module.CLIENT_SERVICES:
            env = result["services"][name]["environment"]
            self.assertTrue(env["KMS_DEMO_ALLOWED_HOSTS"].startswith("${"))
            self.assertIn("https://" + ADDRESS + ":8443", env["KMS_DEMO_ALLOWED_ORIGINS"])
            self.assertEqual(env["KMS_CHAIN_WRITES_ENABLED"], "false")
            self.assertEqual(env["FABRIC_DID_ENABLED"], "false")

    def test_idempotent_configuration(self):
        result = module.configure(self.fixture(), ADDRESS)
        original = copy.deepcopy(result)
        self.assertEqual(module.configure(result, ADDRESS), original)

    def test_list_environment_preserves_values_and_pass_through(self):
        fixture = self.fixture()
        for name in module.CLIENT_SERVICES:
            fixture["services"][name]["environment"] = [
                "KMS_CHAIN_WRITES_ENABLED=false", "FABRIC_DID_ENABLED=false",
                "KMS_DEMO_ALLOWED_HOSTS=${KMS_DEMO_ALLOWED_HOSTS:-localhost:8088}",
                "VALUE_WITH_EQUALS=first=second", "PASS_THROUGH",
            ]
        result = module.configure(fixture, ADDRESS)
        for name in module.CLIENT_SERVICES:
            env = result["services"][name]["environment"]
            self.assertEqual(env["VALUE_WITH_EQUALS"], "first=second")
            self.assertIsNone(env["PASS_THROUGH"])
            self.assertEqual(env["KMS_CHAIN_WRITES_ENABLED"], "false")
            self.assertEqual(env["FABRIC_DID_ENABLED"], "false")
            self.assertIn(ADDRESS + ":8443", env["KMS_DEMO_ALLOWED_HOSTS"])

    @unittest.skipUnless(shutil.which("docker"), "Docker CLI required (daemon not needed)")
    def test_actual_compose_config_without_interpolation(self):
        path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
        process = subprocess.run(["docker", "compose", "-f", str(path), "config",
                                  "--no-interpolate", "--no-path-resolution", "--format", "json"],
                                 capture_output=True, timeout=30)
        # Never include Compose output (which may contain credentials) in failures.
        self.assertEqual(process.returncode, 0, "Offline Compose config failed; output withheld")
        result = module.configure(json.loads(process.stdout), ADDRESS)
        for name in module.CLIENT_SERVICES:
            env = result["services"][name]["environment"]
            self.assertIsInstance(env, dict)
            self.assertIn(ADDRESS + ":8443", env["KMS_DEMO_ALLOWED_HOSTS"])
            self.assertIn("https://" + ADDRESS + ":8443", env["KMS_DEMO_ALLOWED_ORIGINS"])
        round_trip = subprocess.run(["docker", "compose", "-f", "-", "config",
                                     "--no-interpolate", "--no-path-resolution", "--format", "json"],
                                    input=json.dumps(result).encode(), capture_output=True, timeout=30)
        self.assertEqual(round_trip.returncode, 0,
                         "Modified Compose config validation failed; output withheld")

    def test_template_keeps_local_servers_and_is_idempotent(self):
        original = (Path(__file__).resolve().parents[1] /
                    "nginx/demo-server.conf.template").read_text()
        template = module.server_template(original, ADDRESS)
        self.assertTrue(template.startswith(original.replace(
            "listen 443 ssl default_server;", "listen 443 ssl;").rstrip()))
        self.assertIn("return 308 https://" + ADDRESS + ":8443$request_uri;", template)
        self.assertEqual(template.count("# BEGIN KMS SERVER ACCESS"), 1)
        self.assertEqual(module.server_template(template, ADDRESS), template)

    def test_ip_certificate_is_only_tls_default(self):
        original = (Path(__file__).resolve().parents[1] /
                    "nginx/demo-server.conf.template").read_text()
        template = module.server_template(original, ADDRESS)
        self.assertEqual(template.count("listen 443 ssl default_server;"), 1)
        external = template.split("# BEGIN KMS SERVER ACCESS", 1)[1]
        self.assertIn("listen 443 ssl default_server;", external)
        self.assertIn("ssl_certificate /run/kms-server-tls/server.crt;", external)
        self.assertIn("server_name " + ADDRESS + ";", external)
        # Localhost's named TLS server and fail-closed default HTTP remain.
        self.assertIn("server_name 127.0.0.1 localhost;", template)
        self.assertIn("listen 80 default_server;", template)


if __name__ == "__main__":
    unittest.main()
