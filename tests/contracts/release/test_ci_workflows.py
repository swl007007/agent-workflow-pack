from __future__ import annotations

from pathlib import Path

from agent_stack._vendor import yaml


ROOT = Path(__file__).resolve().parents[3]


def load_workflow(name: str) -> dict[str, object]:
    value = yaml.safe_load((ROOT / ".github/workflows" / name).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def step_runs(job: dict[str, object]) -> list[str]:
    steps = job["steps"]
    assert isinstance(steps, list)
    return [str(step.get("run", "")) for step in steps if isinstance(step, dict)]


def assert_frozen_uv(job: dict[str, object]) -> None:
    steps = job["steps"]
    assert isinstance(steps, list)
    setup = next(
        step
        for step in steps
        if isinstance(step, dict) and step.get("uses") == "astral-sh/setup-uv@v6"
    )
    assert setup.get("with") == {"version": "0.11.28"}


def complete_acceptance_command(commands: list[str]) -> str:
    return next(
        command
        for command in commands
        if "tests/unit" in command
        and "tests/contracts" in command
        and "tests/property" in command
        and "tests/golden" in command
        and "tests/integration" in command
        and "tests/concurrency" in command
        and "tests/packaging" in command
        and "tests/e2e" in command
    )


def test_ci_matrix_covers_python_311_through_314_and_artifact_gates() -> None:
    workflow = load_workflow("ci.yml")
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    test_job = jobs["test"]
    assert isinstance(test_job, dict)
    strategy = test_job["strategy"]
    assert isinstance(strategy, dict)
    matrix = strategy["matrix"]
    assert isinstance(matrix, dict)

    assert matrix["python-version"] == ["3.11", "3.12", "3.13", "3.14"]
    assert_frozen_uv(test_job)
    commands = step_runs(test_job)
    assert next(i for i, value in enumerate(commands) if "generate_notices.py --check" in value) < next(
        i for i, value in enumerate(commands) if "build_artifacts.py" in value
    )
    assert any("sync_runtime_vendor.py --check" in value for value in commands)
    assert complete_acceptance_command(commands)

    steps = test_job["steps"]
    assert isinstance(steps, list)
    diagnostic_upload = next(
        step
        for step in steps
        if isinstance(step, dict)
        and step.get("uses") == "actions/upload-artifact@v4"
    )
    assert diagnostic_upload.get("if") == "always()"
    assert diagnostic_upload.get("with") == {
        "name": "release-artifacts-python-${{ matrix.python-version }}",
        "path": "dist/*.whl\ndist/*.tar.gz\ndist/release-artifact-set.json\n",
        "if-no-files-found": "error",
        "retention-days": 1,
    }


def test_release_workflow_orders_build_gate_manifest_publish_and_reverify() -> None:
    workflow = load_workflow("release.yml")
    jobs = workflow["jobs"]
    assert isinstance(jobs, dict)
    build = jobs["build-and-gate"]
    publish = jobs["publish-immutable"]
    assert isinstance(build, dict) and isinstance(publish, dict)
    assert_frozen_uv(build)
    assert_frozen_uv(publish)
    assert publish["needs"] == "build-and-gate"
    build_commands = step_runs(build)
    publish_commands = step_runs(publish)

    assert any("build_artifacts.py" in value for value in build_commands)
    acceptance_index = build_commands.index(complete_acceptance_command(build_commands))
    build_index = next(
        i for i, value in enumerate(build_commands) if "build_artifacts.py" in value
    )
    assert build_index < acceptance_index
    assert not any("release-manifest.json" in value for value in build_commands)
    assert not any("uv build" in value for value in publish_commands)
    verify_index = next(
        i for i, value in enumerate(publish_commands) if "--verify-existing" in value
    )
    publish_index = next(
        i for i, value in enumerate(publish_commands) if "publish_release.py" in value
    )
    reverify_index = next(
        i for i, value in enumerate(publish_commands) if "verify_published_release.py" in value
    )
    assert verify_index < publish_index < reverify_index
    assert "immutable" in repr(publish).casefold()
    for job in (build, publish):
        checkout = next(step for step in job["steps"] if step.get("uses") == "actions/checkout@v4")
        assert checkout["with"] == {
            "ref": "refs/tags/v${{ inputs.version }}",
            "fetch-depth": 0,
            "fetch-tags": True,
        }
        assert any("rev-parse" in command and "status --porcelain" in command for command in step_runs(job))
