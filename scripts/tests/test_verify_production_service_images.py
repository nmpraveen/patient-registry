import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_production_service_images import build_service_image  # noqa: E402


class CommittedServiceBuildTest(unittest.TestCase):
    @patch("verify_production_service_images.subprocess.run")
    @patch("verify_production_service_images.sha256_file", return_value="sha256:" + "a" * 64)
    def test_caddy_builds_exact_committed_dockerfile_to_one_oci(self, _sha256, run) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            context = root / "context"
            output = root / "output"
            (context / "deploy").mkdir(parents=True)
            output.mkdir()
            (context / "deploy" / "Dockerfile.caddy").write_text("FROM scratch\n")
            artifact = output / "caddy-image.oci.tar"
            build_service_image(
                context, output, "builder-name", "caddy", "b" * 40, artifact
            )
        command = run.call_args.args[0]
        self.assertIn(str(context / "deploy" / "Dockerfile.caddy"), command)
        self.assertIn("VCS_REF=" + "b" * 40, command)
        self.assertIn(
            f"type=oci,dest={artifact},tar=true,oci-mediatypes=true", command
        )
        self.assertNotIn("--load", command)


if __name__ == "__main__":
    unittest.main()
