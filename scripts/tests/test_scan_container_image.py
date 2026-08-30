from io import BytesIO
import tarfile
import unittest

from scripts.scan_container_image import forbidden_path, scan_tar_stream


class ImageSecretSignatureRegressionTest(unittest.TestCase):
    def test_only_exact_empty_backup_mountpoint_is_allowed(self) -> None:
        self.assertFalse(forbidden_path("app/backups", is_directory=True))
        self.assertTrue(forbidden_path("app/backups", is_directory=False))
        self.assertTrue(forbidden_path("app/backups/patient.zip", is_directory=False))

    def test_cloud_private_key_marker_is_detected(self) -> None:
        marker = (
            b'{"type": "service_' + b'account", '
            b'"private_' + b'key_id": "synthetic-test-only"}'
        )
        archive = BytesIO()
        with tarfile.open(fileobj=archive, mode="w") as output:
            info = tarfile.TarInfo("app/synthetic-detector-regression.json")
            info.size = len(marker)
            output.addfile(info, BytesIO(marker))
        archive.seek(0)

        findings: list[str] = []
        scan_tar_stream(
            archive,
            canary=None,
            findings=findings,
            source="synthetic-test-layer",
        )

        self.assertEqual(2, len(findings))
        self.assertTrue(all("secret signature" in finding for finding in findings))


if __name__ == "__main__":
    unittest.main()
