import importlib.machinery
import importlib.util
import json
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
OPSCTL = ROOT / "runtime" / "multi-cloud-ssh-mcp" / "opsctl"
WRAPPER = ROOT / "runtime" / "multi-cloud-ssh-mcp" / "opsctl_ssh_wrapper.py"


def load_source(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class OpsctlRealismTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.opsctl = load_source("real_opsctl", OPSCTL)
        cls.source = OPSCTL.read_text(encoding="utf-8")

    def call(self, *args):
        with mock.patch.object(self.opsctl, "run_command", return_value=0) as runner:
            self.opsctl.dispatch(list(args))
        return runner.call_args.args[0]

    def test_no_fixture_or_synthetic_rendering_path_remains(self):
        self.assertNotIn("ops-observations.json", self.source)
        self.assertNotIn("render_", self.source)
        self.assertNotIn("fault_active", self.source)

    def test_host_observation_maps_to_real_binary_argv(self):
        self.assertEqual(self.call("uptime"), ["uptime"])
        self.assertEqual(self.call("free", "-m"), ["free", "-m"])
        self.assertEqual(self.call("vmstat", "1", "3"), ["vmstat", "1", "3"])
        self.assertEqual(
            self.call("sysctl", "net.core.somaxconn"),
            ["sysctl", "net.core.somaxconn"],
        )

    def test_curl_only_reaches_contest_entries(self):
        argv = self.call("curl", "-I", "http://203.0.113.10:18080/")
        self.assertEqual(argv[-1], "http://203.0.113.10:18080/")
        with self.assertRaises(SystemExit):
            self.opsctl.dispatch(["curl", "https://example.com/"])

    def test_gateway_alias_uses_real_gateway_container(self):
        argv = self.call("docker", "logs", "gateway")
        self.assertEqual(argv[:2], ["docker", "logs"])
        self.assertEqual(argv[-1], "mc-robot-gateway")
        argv = self.call("docker", "exec", "gateway", "nginx", "-T")
        self.assertEqual(argv, ["docker", "exec", "mc-robot-gateway", "nginx", "-T"])

    def test_docker_inspect_is_sanitized(self):
        with mock.patch.object(self.opsctl, "container_id", return_value="abc123"), mock.patch.object(
            self.opsctl, "run_command", return_value=0
        ) as runner:
            self.opsctl.dispatch(["docker", "inspect", "shipping"])
        argv = runner.call_args.args[0]
        template = argv[argv.index("--format") + 1]
        self.assertNotIn("Env", template)
        self.assertNotIn("Mounts", template)
        self.assertNotIn("Labels", template)

    def test_mysql_allows_observation_and_denies_writes(self):
        with mock.patch.object(self.opsctl, "compose_exec", return_value=0) as runner:
            self.opsctl.dispatch(["mysql", "-e", "SHOW FULL PROCESSLIST"])
        self.assertIn("SHOW FULL PROCESSLIST", runner.call_args.args[1])
        with self.assertRaises(SystemExit):
            self.opsctl.dispatch(["mysql", "-e", "UPDATE cities.cities SET name='x'"])

    def test_mongodb_allows_explain_and_denies_changes(self):
        expression = (
            'db.getSiblingDB("catalogue").products.find('
            '{categories:"Robot",price:{$gte:100}}).sort({price:1}).explain("executionStats")'
        )
        with mock.patch.object(self.opsctl, "compose_exec", return_value=0) as runner:
            self.opsctl.dispatch(["mongosh", "--quiet", "--eval", expression])
        self.assertEqual(runner.call_args.args[1][-1], expression)
        with self.assertRaises(SystemExit):
            self.opsctl.dispatch(
                ["mongosh", "--quiet", "--eval", 'db.products.dropIndex("categories_1_price_1")']
            )

    def test_arbitrary_docker_exec_and_shell_are_denied(self):
        with self.assertRaises(SystemExit):
            self.opsctl.dispatch(["docker", "exec", "edge", "sh", "-c", "id"])
        with self.assertRaises(SystemExit):
            self.opsctl.dispatch(["bash", "-c", "id"])


class DemoCaseTests(unittest.TestCase):
    def test_public_repository_contains_only_sanitized_demo_cases(self):
        cases = []
        for case_path in (ROOT / "faults").glob("*/case.json"):
            case = json.loads(case_path.read_text(encoding="utf-8"))
            cases.append((case_path.parent.name, case))
        self.assertEqual(
            sorted(name for name, _case in cases),
            ["db_down", "redis_down", "worker_down"],
        )
        self.assertEqual(sorted(case["order_id"] for _name, case in cases), [1, 2, 5])
        for name, case in cases:
            self.assertTrue(case.get("submission_enabled"), name)
            self.assertTrue(case.get("ai_analysis_visible"), name)
            self.assertIn("localhost", case.get("public_case_info", ""))


class ForcedCommandGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = load_source("opsctl_ssh_wrapper", WRAPPER)

    def test_gate_accepts_only_opsctl_readonly_entrypoints(self):
        self.assertEqual(
            self.wrapper.validate_args(["run", "mongosh", "--quiet", "--eval", "db.products.find({})"]),
            ["run", "mongosh", "--quiet", "--eval", "db.products.find({})"],
        )
        for command in (
            ["run", "bash", "-c", "id"],
            ["runtime-gc"],
            ["run"],
        ):
            with self.assertRaises(SystemExit):
                self.wrapper.validate_args(command)

    def test_interactive_or_shell_original_command_is_rejected(self):
        with mock.patch.dict("os.environ", {"SSH_ORIGINAL_COMMAND": ""}, clear=False):
            with self.assertRaises(SystemExit):
                self.wrapper.parse_request()
        with mock.patch.dict(
            "os.environ",
            {"SSH_ORIGINAL_COMMAND": "MC_ROBOT_CLOUD=aliyun opsctl run ps aux; id"},
            clear=False,
        ):
            env, args = self.wrapper.parse_request()
            self.assertEqual(env["MC_ROBOT_CLOUD"], "aliyun")
            self.assertEqual(args[0], "run")


if __name__ == "__main__":
    unittest.main()
