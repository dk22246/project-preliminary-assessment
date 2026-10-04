import io
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import install_node


class InstallNodeTests(unittest.TestCase):
    def _home(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_platform_key_mapping(self):
        cases = [
            ("win32", "AMD64", "win-x64"),
            ("win32", "arm64", "win-arm64"),
            ("darwin", "arm64", "darwin-arm64"),
            ("darwin", "x86_64", "darwin-x64"),
            ("linux", "x86_64", "linux-x64"),
            ("linux", "aarch64", "linux-arm64"),
        ]
        for plat, machine, expected in cases:
            with mock.patch.object(install_node.sys, "platform", plat), mock.patch.object(install_node.platform, "machine", return_value=machine):
                self.assertEqual(install_node.platform_key(), expected)

    def test_archive_suffix(self):
        self.assertEqual(install_node.archive_suffix("win-x64"), "zip")
        self.assertEqual(install_node.archive_suffix("darwin-arm64"), "tar.gz")
        self.assertEqual(install_node.archive_suffix("linux-x64"), "tar.xz")

    def test_dist_url(self):
        with mock.patch.object(install_node, "platform_key", return_value="win-x64"), mock.patch.object(install_node, "dist_version", return_value="22.14.0"):
            self.assertEqual(install_node.dist_url(), "https://nodejs.org/dist/v22.14.0/node-v22.14.0-win-x64.zip")

    def test_portable_node_candidates_empty_when_no_home(self):
        self.assertEqual(install_node.portable_node_candidates(home=self._home() / "nope"), [])

    def test_portable_node_candidates_finds_exe(self):
        home = self._home()
        install_dir = home / "node-v22.14.0-win-x64"
        exe = install_node._node_executable(install_dir)
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        self.assertIn(exe.resolve(), [p.resolve() for p in install_node.portable_node_candidates(home=home)])

    def test_ensure_node_reuses_existing(self):
        home = self._home()
        install_dir = home / "node-v22.14.0-win-x64"
        exe = install_node._node_executable(install_dir)
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"")
        with mock.patch.object(install_node, "_valid_version", return_value=True), mock.patch.object(install_node, "_download") as dl:
            self.assertEqual(install_node.ensure_node(home=home).resolve(), exe.resolve())
            dl.assert_not_called()

    def test_ensure_node_download_failure_returns_none(self):
        home = self._home()
        with mock.patch.object(install_node, "_valid_version", return_value=False), mock.patch.object(install_node, "_download", side_effect=OSError("no net")):
            self.assertIsNone(install_node.ensure_node(home=home, version="22.14.0"))

    def test_ensure_node_downloads_and_unpacks(self):
        home = self._home()

        def fake_download(url, dest):
            with zipfile.ZipFile(dest, "w") as zf:
                zf.writestr("node-v22.14.0-win-x64/node.exe", "fake")

        with mock.patch.object(install_node, "_download", side_effect=fake_download), mock.patch.object(install_node, "_valid_version", return_value=True), mock.patch.object(install_node, "platform_key", return_value="win-x64"), mock.patch.object(install_node, "dist_version", return_value="22.14.0"):
            exe = install_node.ensure_node(home=home)

        self.assertIsNotNone(exe)
        self.assertTrue(exe.is_file())
        self.assertTrue((home / "node-v22.14.0-win-x64").is_dir())

    def test_extract_tar_gz(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        archive = root / "x.tar.gz"
        with tarfile.open(archive, "w:gz") as tf:
            data = b"payload"
            info = tarfile.TarInfo("bin/node")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        out = root / "out"
        install_node._extract(archive, out)
        self.assertTrue((out / "bin" / "node").is_file())

    def test_extract_tar_xz(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        archive = root / "x.tar.xz"
        with tarfile.open(archive, "w:xz") as tf:
            data = b"payload"
            info = tarfile.TarInfo("bin/node")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
        out = root / "out"
        install_node._extract(archive, out)
        self.assertTrue((out / "bin" / "node").is_file())


if __name__ == "__main__":
    unittest.main()
