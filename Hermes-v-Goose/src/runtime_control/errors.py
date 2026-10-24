"""Errors shared by the control module and its clients. Imports nothing heavy, so
short-lived shim processes (for example a goose hook) can load it quickly."""

from __future__ import annotations


class ControlError(Exception):
    """A refused control-plane request. ``code`` is stable and machine-readable."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


class ToolArgumentError(ValueError):
    """Raised by an environment when a tool call's arguments are outside the tool's contract."""


class ControlUnavailable(RuntimeError):
    """The control module could not be reached or did not answer in time."""

    code = "control_unavailable"
