import subprocess

import pytest

from components.api.tool_handlers import _download_file_from_git
from components.settings import get_settings


class TestGitRepositoryFileRetrieval:
    def test_default_branch_file(self, monkeypatch: pytest.MonkeyPatch):
        def _mock_side_effect(cmd, *args, **kwargs):
            if cmd == ["git", "init", "--bare"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "remote",
                "add",
                "origin",
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
            ]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == ["git", "fetch", "--depth=1", "origin"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == ["git", "remote", "set-head", "origin", "--auto"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == ["git", "symbolic-ref", "refs/remotes/origin/HEAD"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="refs/remotes/origin/main\n",
                    stderr="",
                )

            if cmd == ["git", "show", "origin/main:toolforge.yaml"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="ponies are just less interesting unicorns\n",
                    stderr="",
                )

            raise RuntimeError(f"Unknown command executed: {cmd}")

        monkeypatch.setattr(subprocess, "run", _mock_side_effect)

        get_settings().temporary_writable_directory = "/tmp"
        assert (
            _download_file_from_git(
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
                "toolforge.yaml",
            )
            == "ponies are just less interesting unicorns\n"
        )

    def test_explicit_branch_file(self, monkeypatch: pytest.MonkeyPatch):
        def _mock_side_effect(cmd, *args, **kwargs):
            if cmd == ["git", "init", "--bare"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "remote",
                "add",
                "origin",
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
            ]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == ["git", "fetch", "--depth=1", "origin", "very-important-branch"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == ["git", "show", "origin/very-important-branch:toolforge.yaml"]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="ponies are just less interesting unicorns\n",
                    stderr="",
                )

            raise RuntimeError(f"Unknown command executed: {cmd}")

        monkeypatch.setattr(subprocess, "run", _mock_side_effect)

        get_settings().temporary_writable_directory = "/tmp"
        assert (
            _download_file_from_git(
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
                "toolforge.yaml",
                "very-important-branch",
            )
            is not None
        )

    def test_missing_branch(self, monkeypatch: pytest.MonkeyPatch):
        def _mock_side_effect(cmd, *args, **kwargs):
            if cmd == ["git", "init", "--bare"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "remote",
                "add",
                "origin",
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
            ]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "fetch",
                "--depth=1",
                "origin",
                "ref-does-not-exist-in-remote",
            ]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "show",
                "origin/ref-does-not-exist-in-remote:toolforge.yaml",
            ]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=128,
                    stdout="",
                    stderr="fatal: invalid object name 'origin/ref-does-not-exist-in-remote'.",
                )

            raise RuntimeError(f"Unknown command executed: {cmd}")

        monkeypatch.setattr(subprocess, "run", _mock_side_effect)

        get_settings().temporary_writable_directory = "/tmp"
        with pytest.raises(ValueError) as excinfo:
            _download_file_from_git(
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
                "toolforge.yaml",
                "ref-does-not-exist-in-remote",
            )

        assert str(excinfo.value) == (
            "git failed to show 'toolforge.yaml' for ref 'origin/ref-does-not-exist-in-remote' in remote "
            "'https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git'"
        )

    def test_missing_file(self, monkeypatch: pytest.MonkeyPatch):
        def _mock_side_effect(cmd, *args, **kwargs):
            if cmd == ["git", "init", "--bare"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "remote",
                "add",
                "origin",
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
            ]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == ["git", "fetch", "--depth=1", "origin", "main"]:
                return subprocess.CompletedProcess(
                    args=[], returncode=0, stdout="", stderr=""
                )

            if cmd == [
                "git",
                "show",
                "origin/main:some-file-path-that-does-not-exist.yaml",
            ]:
                return subprocess.CompletedProcess(
                    args=[],
                    returncode=128,
                    stdout="",
                    stderr="fatal: path 'some-file-path-that-does-not-exist.yaml' does not exist in 'origin/main'",
                )

            raise RuntimeError(f"Unknown command executed: {cmd}")

        monkeypatch.setattr(subprocess, "run", _mock_side_effect)

        get_settings().temporary_writable_directory = "/tmp"
        with pytest.raises(ValueError) as excinfo:
            _download_file_from_git(
                "https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git",
                "some-file-path-that-does-not-exist.yaml",
                "main",
            )

        assert str(excinfo.value) == (
            "git failed to show 'some-file-path-that-does-not-exist.yaml' for ref 'origin/main' in remote "
            "'https://gitlab.wikimedia.org/repos/cloud/toolforge/components-api.git'"
        )
