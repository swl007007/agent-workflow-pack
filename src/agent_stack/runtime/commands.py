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


run_workspace_register = _workspace_registration_required
run_workspace_migrate = _workspace_registration_required
run_task_runtime_load = _task_authority_required
run_task_admit = _task_authority_required
run_task_claim = _task_authority_required
run_task_transition = _task_authority_required
run_task_release = _task_authority_required
run_task_archive = _task_authority_required
run_task_recover = _task_authority_required


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
