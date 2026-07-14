"""Thin lifecycle command composition and presentation."""

from .dispatch import CLIResult, VerifiedRuntimeContext, compose_lifecycle_command
from .output import render_cli_human, render_cli_json
from .parser import CLIUsageError, CommandInvocation, parse_cli_args

__all__ = [
    "CLIResult",
    "CLIUsageError",
    "CommandInvocation",
    "VerifiedRuntimeContext",
    "compose_lifecycle_command",
    "parse_cli_args",
    "render_cli_human",
    "render_cli_json",
]
