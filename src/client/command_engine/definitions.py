from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

type ArgDict = dict[str, str]
type AppliedFlags = list[str]
type CommandPath = tuple[str, ...]
type ArgumentValidator = Callable[[str], tuple[bool, ArgumentError | None]]
type CommandHandler = Callable[[ArgDict, AppliedFlags], CmdExecutionResult]


# ---------------------------------------------------------------------------
# Argument definitions and execution results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArgumentError:
    message: str
    help: str = ""


@dataclass(frozen=True)
class NamedArgument:
    name: str
    required: bool
    validator: ArgumentValidator

    def __post_init__(self) -> None:
        if not self.name or self.name.isdigit():
            raise ValueError("Argument name must be non-empty and non-numeric.")


@dataclass(frozen=True)
class PositionalArgument:
    position: int
    validator: ArgumentValidator

    def __post_init__(self) -> None:
        if self.position < 0:
            raise ValueError("Positional argument index cannot be negative.")


class CmdExecutionCode(Enum):
    Error = auto()
    Success = auto()


@dataclass(frozen=True)
class CmdExecutionResult:
    cmd_execution_code: CmdExecutionCode
    value: Any | None = None

    @classmethod
    def success(cls, value: Any | None = None) -> CmdExecutionResult:
        return cls(CmdExecutionCode.Success, value)

    @classmethod
    def error(cls, message: str) -> CmdExecutionResult:
        return cls(CmdExecutionCode.Error, message)


# ---------------------------------------------------------------------------
# Command definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Command:
    cmd_path: CommandPath
    handler: CommandHandler
    description: str = ""
    arguments: tuple[NamedArgument | PositionalArgument, ...] = ()
    allowed_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # Normalize sequences so a frozen Command cannot retain mutable lists.
        object.__setattr__(self, "cmd_path", tuple(self.cmd_path))
        object.__setattr__(self, "arguments", tuple(self.arguments))
        object.__setattr__(self, "allowed_flags", tuple(self.allowed_flags))

    @staticmethod
    def new_cmd_path(*parts: str) -> CommandPath:
        return parts

    def validate_definition(self) -> list[str]:
        errors: list[str] = []
        named_names: set[str] = set()
        positional_positions: set[int] = set()

        if not self.cmd_path or any(not part for part in self.cmd_path):
            errors.append("Command path must contain non-empty parts.")

        for argument in self.arguments:
            if isinstance(argument, NamedArgument):
                if argument.name in named_names:
                    errors.append(f"Duplicate named argument: {argument.name}")
                named_names.add(argument.name)

            elif isinstance(argument, PositionalArgument):
                if argument.position in positional_positions:
                    errors.append(
                        f"Duplicate positional argument index: {argument.position}"
                    )
                positional_positions.add(argument.position)

        if positional_positions:
            expected_positions = set(range(max(positional_positions) + 1))
            missing_positions = expected_positions - positional_positions
            if missing_positions:
                errors.append(
                    "Positional argument indices must be contiguous from 0; "
                    f"missing: {sorted(missing_positions)}"
                )

        if len(set(self.allowed_flags)) != len(self.allowed_flags):
            errors.append("Duplicate allowed flag.")

        if any(not flag for flag in self.allowed_flags):
            errors.append("Allowed flags cannot be empty.")

        return errors

    def get_named_argument(self, name: str) -> NamedArgument | None:
        return next(
            (
                argument
                for argument in self.arguments
                if isinstance(argument, NamedArgument) and argument.name == name
            ),
            None,
        )

    def get_positional_argument(self, position: int) -> PositionalArgument | None:
        return next(
            (
                argument
                for argument in self.arguments
                if isinstance(argument, PositionalArgument)
                and argument.position == position
            ),
            None,
        )

    def is_allowed_flag(self, flag: str) -> bool:
        return flag in self.allowed_flags

    def is_allowed_arg_name(self, arg_name: str) -> bool:
        return self.get_named_argument(arg_name) is not None

    def is_allowed_arg_position(self, position: int) -> bool:
        return self.get_positional_argument(position) is not None

    def get_validator_for_argument(self, arg_name: str) -> ArgumentValidator | None:
        argument = self.get_named_argument(arg_name)
        return argument.validator if argument else None

    def get_validator_for_pos_argument(self, position: int) -> ArgumentValidator | None:
        argument = self.get_positional_argument(position)
        return argument.validator if argument else None


# ---------------------------------------------------------------------------
# Token definitions
# ---------------------------------------------------------------------------


class CommandTokenType(Enum):
    WORD = auto()
    PATH = auto()
    VALUE = auto()
    MULTI_WORD_FLAG = auto()
    SINGLE_CHAR_FLAG = auto()
    ARG_NAME = auto()


@dataclass
class CommandToken:
    token_type: CommandTokenType
    value: str
