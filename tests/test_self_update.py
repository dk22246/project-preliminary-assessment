import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import self_update


class SelfUpdateTests(unittest.TestCase):
    def _base(self) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        (base / ".git" / "refs" / "heads").mkdir(parents=True)
        return base

    def test_non_git_deploy_skips(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)  # 无 .git
        with mock.patch.object(self_update, "_run") as run:
            self.assertIsNone(self_update.ensure_fresh(root=base))
            run.assert_not_called()

    def test_ttl_skips_network(self):
        base = self._base()
        (base / ".self-update-marker").write_text(str(int(time.time())), encoding="utf-8")
        with mock.patch.object(self_update, "_run") as run:
            self.assertIsNone(self_update.ensure_fresh(root=base))
            run.assert_not_called()

    def test_up_to_date_returns_silently(self):
        base = self._base()
        calls = []

        def fake_run(*args, cwd=None):
            calls.append(args)
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return "same"
            if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
                return "main"
            if args[0] == "ls-remote":
                return "same\trefs/heads/main"
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))
        self.assertFalse(any("fetch" in c for c in calls))

    def test_wrong_branch_no_update(self):
        base = self._base()

        def fake_run(*args, cwd=None):
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return "local"
            if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
                return "codex/execution-chain-rebuild"
            if args[0] == "ls-remote":
                return "remote\trefs/heads/main"
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))
        self.assertFalse((base / ".git" / "refs" / "heads" / "main").exists())

    def test_dirty_worktree_skips(self):
        base = self._base()

        def fake_run(*args, cwd=None):
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return "local"
            if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
                return "main"
            if args[0] == "ls-remote":
                return "remote\trefs/heads/main"
            if args[0] == "status":
                return " M dirty.txt"
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))

    def test_fast_forward_updates(self):
        base = self._base()

        def fake_run(*args, cwd=None):
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return "aaa1111"
            if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
                return "main"
            if args[0] == "ls-remote":
                return "bbb2222\trefs/heads/main"
            if args[0] == "status":
                return ""
            if args[0] == "fetch":
                return ""
            if args[0] == "rev-parse" and args[1] == "FETCH_HEAD":
                return "bbb2222"
            if args[0] == "merge-base":
                return ""
            if args[0] == "checkout":
                return ""
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))
        ref = base / ".git" / "refs" / "heads" / "main"
        self.assertTrue(ref.exists())
        self.assertEqual(ref.read_text().strip(), "bbb2222")

    def test_non_ancestor_no_update(self):
        base = self._base()

        def fake_run(*args, cwd=None):
            if args[0] == "rev-parse" and args[1] == "HEAD":
                return "aaa1111"
            if args[0] == "rev-parse" and args[1] == "--abbrev-ref":
                return "main"
            if args[0] == "ls-remote":
                return "bbb2222\trefs/heads/main"
            if args[0] == "status":
                return ""
            if args[0] == "fetch":
                return ""
            if args[0] == "rev-parse" and args[1] == "FETCH_HEAD":
                return "bbb2222"
            if args[0] == "merge-base":
                raise RuntimeError("not ancestor")
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))
        self.assertFalse((base / ".git" / "refs" / "heads" / "main").exists())

    def test_git_missing_degrades(self):
        base = self._base()
        with mock.patch.object(self_update, "shutil") as shutil_mock:
            shutil_mock.which.return_value = None
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))


if __name__ == "__main__":
    unittest.main()
