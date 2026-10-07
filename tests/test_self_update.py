import sys
import subprocess
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
            self.assertEqual(self_update.ensure_fresh(quiet=True, root=base), "blocked")
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
            self.assertEqual(self_update.ensure_fresh(quiet=True, root=base), "blocked")

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
            if args[0] == "merge":
                return ""
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertEqual(self_update.ensure_fresh(quiet=True, root=base), "updated")
        self.assertFalse((base / ".git" / "refs" / "heads" / "main").exists())

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
            self.assertEqual(self_update.ensure_fresh(quiet=True, root=base), "blocked")
        self.assertFalse((base / ".git" / "refs" / "heads" / "main").exists())

    def test_local_ahead_of_remote_continues_without_downgrade(self):
        base = self._base()

        def fake_run(*args, cwd=None):
            if args[:2] == ("rev-parse", "HEAD"):
                return "local-newer"
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "main"
            if args[0] == "ls-remote":
                return "remote-older\trefs/heads/main"
            if args[0] == "status":
                return ""
            if args[0] == "fetch":
                return ""
            if args[:2] == ("rev-parse", "FETCH_HEAD"):
                return "remote-older"
            if args == ("merge-base", "--is-ancestor", "local-newer", "remote-older"):
                raise RuntimeError("local is not ancestor")
            if args == ("merge-base", "--is-ancestor", "remote-older", "local-newer"):
                return ""
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))

    def test_fast_forward_failure_blocks_instead_of_continuing_old_code(self):
        base = self._base()

        def fake_run(*args, cwd=None):
            if args[:2] == ("rev-parse", "HEAD"):
                return "local"
            if args[:2] == ("rev-parse", "--abbrev-ref"):
                return "main"
            if args[0] == "ls-remote":
                return "remote\trefs/heads/main"
            if args[0] in {"status", "fetch"}:
                return ""
            if args[:2] == ("rev-parse", "FETCH_HEAD"):
                return "remote"
            if args[0] == "merge-base":
                return ""
            if args[0] == "merge":
                raise RuntimeError("untracked file would be overwritten")
            raise AssertionError(f"unexpected: {args}")

        with mock.patch.object(self_update, "_run", side_effect=fake_run):
            self.assertEqual(self_update.ensure_fresh(quiet=True, root=base), "blocked")

    def test_git_missing_degrades(self):
        base = self._base()
        with mock.patch.object(self_update, "shutil") as shutil_mock:
            shutil_mock.which.return_value = None
            self.assertIsNone(self_update.ensure_fresh(quiet=True, root=base))

    def test_real_git_worktree_fast_forwards_without_writing_git_internals(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        remote = root / "remote.git"
        seed = root / "seed"
        manager = root / "manager"
        deployed = root / "deployed"

        def git(*args: str, cwd: Path | None = None) -> str:
            result = subprocess.run(
                ["git", *args], cwd=cwd, text=True, encoding="utf-8",
                errors="replace", capture_output=True, check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.strip()

        git("init", "--bare", str(remote))
        git("init", str(seed))
        git("config", "user.email", "tests@example.com", cwd=seed)
        git("config", "user.name", "Tests", cwd=seed)
        (seed / "version.txt").write_text("v1\n", encoding="utf-8")
        git("add", "version.txt", cwd=seed)
        git("commit", "-m", "v1", cwd=seed)
        git("branch", "-M", "main", cwd=seed)
        git("remote", "add", "origin", str(remote), cwd=seed)
        git("push", "-u", "origin", "main", cwd=seed)
        git("symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)

        git("clone", str(remote), str(manager))
        git("checkout", "-b", "holder", cwd=manager)
        git("worktree", "add", str(deployed), "main", cwd=manager)
        self.assertTrue((deployed / ".git").is_file(), "test must exercise a real linked worktree")

        (seed / "version.txt").write_text("v2\n", encoding="utf-8")
        git("add", "version.txt", cwd=seed)
        git("commit", "-m", "v2", cwd=seed)
        git("push", "origin", "main", cwd=seed)

        result = self_update.ensure_fresh(quiet=True, root=deployed)

        self.assertEqual(result, "updated")
        self.assertEqual((deployed / "version.txt").read_text(encoding="utf-8"), "v2\n")
        self.assertEqual(git("rev-parse", "HEAD", cwd=deployed), git("rev-parse", "main", cwd=seed))


if __name__ == "__main__":
    unittest.main()
