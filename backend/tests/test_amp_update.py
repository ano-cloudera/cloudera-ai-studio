"""scripts/amp/update.py: pull from GitHub and redeploy, run against real throwaway git repositories."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("amp_update", REPO / "scripts" / "amp" / "update.py")
up = importlib.util.module_from_spec(_spec)
sys.modules["amp_update"] = up
_spec.loader.exec_module(up)


def sh(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return done.stdout.strip()


@pytest.fixture
def pair(tmp_path):
    """A bare 'GitHub', a project clone of it (the CAI project) and a second clone that pushes new work."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(origin)], check=True, capture_output=True)
    pusher = tmp_path / "pusher"
    subprocess.run(["git", "clone", str(origin), str(pusher)], check=True, capture_output=True)
    (pusher / "app.txt").write_text("one\n")
    sh(pusher, "add", "-A"); sh(pusher, "commit", "-m", "first"); sh(pusher, "push", "-u", "origin", "HEAD:main")
    project = tmp_path / "project"
    subprocess.run(["git", "clone", str(origin), str(project)], check=True, capture_output=True)
    return project, pusher


def push(pusher: Path, name: str, text: str, message: str) -> None:
    target = pusher / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    sh(pusher, "add", "-A"); sh(pusher, "commit", "-m", message); sh(pusher, "push", "origin", "HEAD:main")


def test_new_commits_are_pulled_and_reported(pair) -> None:
    project, pusher = pair
    push(pusher, "app.txt", "two\n", "second")
    push(pusher, "backend/requirements.txt", "x\n", "third")
    result = up.pull(project)
    assert result.ok and result.changed
    assert [line.split(" ", 1)[1] for line in result.commits] == ["third", "second"]
    assert sorted(result.files) == ["app.txt", "backend/requirements.txt"]
    assert (project / "app.txt").read_text() == "two\n"
    assert up.needs_backend_install(result.files) and not up.needs_backend_install(["app.txt", "frontend/package.json"])


def test_nothing_new_changes_nothing(pair) -> None:
    project, _ = pair
    result = up.pull(project)
    assert result.ok and not result.changed and result.commits == []


def test_a_local_edit_that_is_in_the_way_stops_the_pull_and_is_kept(pair) -> None:
    project, pusher = pair
    (project / "app.txt").write_text("mine\n")
    push(pusher, "app.txt", "theirs\n", "second")
    result = up.pull(project)
    assert not result.ok and "git stash" in result.message and "app.txt" in result.message
    assert (project / "app.txt").read_text() == "mine\n"  # never discarded


def test_a_diverged_branch_is_not_merged(pair) -> None:
    project, pusher = pair
    (project / "local.txt").write_text("local\n")
    sh(project, "add", "-A"); sh(project, "commit", "-m", "local only")
    push(pusher, "app.txt", "two\n", "remote")
    before = sh(project, "rev-parse", "HEAD")
    result = up.pull(project)
    assert not result.ok and "not on GitHub" in result.message
    assert sh(project, "rev-parse", "HEAD") == before


def test_a_folder_that_is_not_a_repository_and_a_detached_head_say_so(tmp_path, pair) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    assert "not a git repository" in up.pull(plain).message
    project, _ = pair
    sh(project, "checkout", "--detach")
    assert "detached" in up.pull(project).message


def test_credentials_in_a_url_are_masked() -> None:
    assert up.mask("fatal: unable to access 'https://user:ghp_secret@github.com/x/y.git/'") == "fatal: unable to access 'https://***@github.com/x/y.git/'"


def test_the_job_deploys_only_when_something_changed_or_when_forced(pair, monkeypatch, capsys) -> None:
    project, pusher = pair
    deployed: list[Path] = []
    monkeypatch.setattr(up, "ROOT", project)
    monkeypatch.setattr(up, "run_deploy", lambda root: deployed.append(root) or 0)
    monkeypatch.setattr(up, "install_backend", lambda root: pytest.fail("requirements did not change"))

    assert up.main([]) == 0 and deployed == []  # already up to date
    assert "Already up to date" in capsys.readouterr().out
    assert up.main(["--force-deploy"]) == 0 and deployed == [project]

    push(pusher, "app.txt", "two\n", "second")
    assert up.main(["--no-deploy"]) == 0 and deployed == [project]  # pulled, not deployed
    push(pusher, "app.txt", "three\n", "third")
    assert up.main([]) == 0 and deployed == [project, project]
    assert "1 commit(s), 1 file(s) changed" in capsys.readouterr().out


def test_requirements_are_installed_before_the_deploy_and_a_failed_install_stops_it(pair, monkeypatch) -> None:
    project, pusher = pair
    order: list[str] = []
    monkeypatch.setattr(up, "ROOT", project)
    monkeypatch.setattr(up, "install_backend", lambda root: order.append("pip") or 0)
    monkeypatch.setattr(up, "run_deploy", lambda root: order.append("deploy") or 0)
    push(pusher, "backend/requirements.txt", "x\n", "deps")
    assert up.main([]) == 0 and order == ["pip", "deploy"]

    order.clear()
    monkeypatch.setattr(up, "install_backend", lambda root: order.append("pip") or 1)
    push(pusher, "backend/requirements.txt", "y\n", "more deps")
    assert up.main([]) == 1 and order == ["pip"]


def test_check_reports_waiting_commits_without_changing_the_project(pair, capsys) -> None:
    project, pusher = pair
    assert up.check(project) == 0 and "Up to date" in capsys.readouterr().out
    push(pusher, "app.txt", "two\n", "second")
    head = sh(project, "rev-parse", "HEAD")
    assert up.check(project) == 0 and "1 new commit(s)" in capsys.readouterr().out
    assert sh(project, "rev-parse", "HEAD") == head
