"""Thin lifecycle command composition and presentation."""

from .dispatch import CLIResult, VerifiedRuntimeContext, compose_lifecycle_command
from .output import render_cli_human, render_cli_json
from .parser import CLIUsageError, CommandInvocation, parse_cli_args
from .production import compose_production_runtime_context, production_owner_bindings

__all__ = [
    "CLIResult",
    "CLIUsageError",
    "CommandInvocation",
    "VerifiedRuntimeContext",
    "compose_lifecycle_command",
    "compose_production_runtime_context",
    "parse_cli_args",
    "production_owner_bindings",
    "render_cli_human",
    "render_cli_json",
]
