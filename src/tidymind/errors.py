"""Exception types and stable exit codes (SRS section 7)."""

from __future__ import annotations

EXIT_OK = 0
EXIT_INTERNAL = 1  # unexpected internal error (use --debug for a traceback)
EXIT_USAGE = 2  # bad arguments or configuration (argparse also uses 2)
EXIT_INPUT = 3  # missing/unreadable directory, plan file, or output path
EXIT_MODEL = 4  # local model/runtime unavailable or returned unusable output
EXIT_PLAN_INVALID = 5  # malformed plan, unsupported schema, root mismatch
EXIT_CANCELLED = 6  # user did not approve; nothing was changed
EXIT_INCOMPLETE = 7  # some operations were skipped or failed


class TidyMindError(Exception):
    """Base class for expected, user-actionable errors."""

    exit_code = EXIT_INTERNAL


class ConfigError(TidyMindError):
    exit_code = EXIT_USAGE


class InputError(TidyMindError):
    exit_code = EXIT_INPUT


class ScanError(InputError):
    pass


class ModelError(TidyMindError):
    exit_code = EXIT_MODEL


class ModelUnavailableError(ModelError):
    """Ollama is not reachable, timed out, or the model is missing."""


class ModelResponseError(ModelError):
    """The model answered, but not with a valid, schema-conforming response."""


class PlanError(TidyMindError):
    exit_code = EXIT_PLAN_INVALID


class PlanFormatError(PlanError):
    """The plan file is malformed or uses an unsupported schema."""


class RootMismatchError(PlanError):
    """The plan root is not the directory that execution would use."""


class NoClobberUnsupportedError(OSError):
    """The platform/filesystem cannot guarantee a no-overwrite rename."""
