import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class ContainerVexRegressionTest(unittest.TestCase):
    def run_verifier(self, report: dict, policy: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report_path = root / "report.json"
            policy_path = root / "policy.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            policy_path.write_text(json.dumps(policy), encoding="utf-8")
            return subprocess.run(
                [
                    sys.executable,
                    "scripts/verify_container_vulnerabilities.py",
                    "--report",
                    str(report_path),
                    "--policy",
                    str(policy_path),
                    "--image-digest",
                    "sha256:" + "a" * 64,
                ],
                capture_output=True,
                text=True,
            )

    def test_clean_report_and_empty_policy_pass(self) -> None:
        result = self.run_verifier(
            {"Results": []},
            {"schema": "medtrack.container-vex/v1", "entries": []},
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("high=0 critical=0 waivers=0", result.stdout)

    def test_new_finding_fails_closed(self) -> None:
        result = self.run_verifier(
            {
                "Results": [
                    {
                        "Target": "alpine",
                        "Vulnerabilities": [
                            {
                                "VulnerabilityID": "CVE-2099-0001",
                                "PkgName": "example",
                                "InstalledVersion": "1.0",
                                "Severity": "CRITICAL",
                                "Status": "affected",
                            }
                        ],
                    }
                ]
            },
            {"schema": "medtrack.container-vex/v1", "entries": []},
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("unwaived finding CRITICAL CVE-2099-0001", result.stderr)

    def test_secret_finding_cannot_be_waived(self) -> None:
        result = self.run_verifier(
            {
                "Results": [
                    {
                        "Target": "app/example.json",
                        "Secrets": [
                            {"RuleID": "synthetic-secret", "StartLine": 1}
                        ],
                    }
                ]
            },
            {"schema": "medtrack.container-vex/v1", "entries": []},
        )
        self.assertNotEqual(0, result.returncode)
        self.assertIn("secret finding rule=synthetic-secret", result.stderr)


if __name__ == "__main__":
    unittest.main()
