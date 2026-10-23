import json
import sys
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from verify_production_service_images import build_service_image, runtime_smoke  # noqa: E402
from build_canonical_image import verify_loaded_config_digest  # noqa: E402


class LoadedImageIdentityTest(unittest.TestCase):
    @patch("build_canonical_image.subprocess.run")
    def test_classic_store_config_id_needs_no_conversion(self, run) -> None:
        digest = "sha256:" + "a" * 64
        verify_loaded_config_digest(digest, digest)
        run.assert_not_called()

    @patch("build_canonical_image.subprocess.run")
    def test_containerd_manifest_id_binds_to_expected_config(self, run) -> None:
        image_id, config = "sha256:" + "a" * 64, "sha256:" + "b" * 64
        run.return_value.stdout = json.dumps({"config": {"digest": config}})
        verify_loaded_config_digest(image_id, config)
        self.assertEqual(run.call_args.args[0][-1], f"docker-daemon:{image_id}")

    @patch("build_canonical_image.subprocess.run")
    def test_wrong_or_missing_containerd_config_fails_closed(self, run) -> None:
        for manifest in ({"config": {"digest": "sha256:" + "c" * 64}}, {}):
            with self.subTest(manifest=manifest):
                run.return_value.stdout = json.dumps(manifest)
                with self.assertRaisesRegex(RuntimeError, "does not match"):
                    verify_loaded_config_digest("sha256:" + "a" * 64, "sha256:" + "b" * 64)


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

    @patch("verify_production_service_images.load_oci_archive")
    @patch("verify_production_service_images.subprocess.run")
    def test_caddy_runtime_smoke_proves_http_readiness(self, run, _load) -> None:
        revision = "b" * 40
        image_id = "sha256:" + "c" * 64
        run.return_value.stdout = json.dumps(
            [
                {
                    "Id": image_id,
                    "Config": {
                        "User": "10002:10001",
                        "Labels": {"org.opencontainers.image.revision": revision},
                    },
                }
            ]
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "deploy").mkdir()
            (root / "deploy" / "Caddyfile").write_text("{\n}\n")
            runtime_smoke(root, "caddy", root / "caddy.oci.tar", revision, image_id)

        command = run.call_args_list[-1].args[0]
        shell = command[-1]
        self.assertIn("wget -q -O /dev/null http://127.0.0.1/", shell)
        self.assertIn('test "$caddy_ready" = 1', shell)
        self.assertNotIn("bind_status", shell)
        self.assertIn("no-new-privileges:true", command)


if __name__ == "__main__":
    unittest.main()
