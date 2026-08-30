import sys
from pathlib import Path
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_production_service_images import copy_registry_image  # noqa: E402


class RegistryCopyTest(unittest.TestCase):
    @patch("verify_production_service_images.subprocess.run")
    def test_copy_uses_digest_only_reference(self, run) -> None:
        artifact = Path("output/caddy-image.oci.tar")
        with patch.object(Path, "unlink"):
            copy_registry_image(
                "registry.example:5000/team/caddy:release@sha256:" + "a" * 64,
                artifact,
            )
        command = run.call_args.args[0]
        self.assertIn(
            "docker://registry.example:5000/team/caddy@sha256:" + "a" * 64,
            command,
        )
        self.assertNotIn(
            "docker://registry.example:5000/team/caddy:release@sha256:" + "a" * 64,
            command,
        )


if __name__ == "__main__":
    unittest.main()
