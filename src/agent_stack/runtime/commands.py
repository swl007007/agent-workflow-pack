"""Production Runtime/Task-state command adapters.

The closed CLI grammar does not itself manufacture the verified manifests,
journals, approvals, or task contracts required by the domain services.  Until
those authorities are present in an initialized project, these adapters fail
with the owning domain's closed errors rather than falling through to an
internal import/composition failure.
"""

from __future__ import annotations

from .errors import RuntimeFailure


def _workspace_registration_required(payload: object) -> object:
    raise RuntimeFailure(
        "AWP_WORKSPACE_REGISTRATION_REQUIRED",
        "command requires a verified initialized workspace contract",
    )


def _task_authority_required(payload: object) -> object:
    raise RuntimeFailure(
        "AWP_TASK_RUNTIME_LOAD_DENIED",
        "command requires verified task integration and transaction authority",
    )


def run_workspace_register(payload: object) -> object:
    return _workspace_registration_required(payload)


def run_workspace_migrate(payload: object) -> object:
    return _workspace_registration_required(payload)


def run_task_runtime_load(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_admit(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_claim(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_transition(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_release(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_archive(payload: object) -> object:
    return _task_authority_required(payload)


def run_task_recover(payload: object) -> object:
    return _task_authority_required(payload)


__all__ = [
    "run_task_admit",
    "run_task_archive",
    "run_task_claim",
    "run_task_recover",
    "run_task_release",
    "run_task_runtime_load",
    "run_task_transition",
    "run_workspace_migrate",
    "run_workspace_register",
]
