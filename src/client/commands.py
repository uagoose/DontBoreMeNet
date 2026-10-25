from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
from types import MappingProxyType
from uuid import uuid4
import re

type ArgumentValidator = Callable[[str], tuple[bool, ArgumentError | None]]
type ArgDict = dict[str, str]
type AppliedFlags = list[str]
type CommandPath = tuple[str, ...]


@dataclass(frozen=True)
class ArgumentError:
    message: str
    help: str = field(default="")


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


class CmdExecutionCode(Enum):
    Error = auto()
    Success = auto()


@dataclass(frozen=True)
class CmdExecutionResult:
    cmd_execution_code: CmdExecutionCode
    value: Any | str | None = field(default=None)


@dataclass(frozen=True)
class Command:
    cmd_path: CommandPath
    handler: Callable[[ArgDict, AppliedFlags], CmdExecutionResult]
    description: str = field(default="")
    arguments: tuple[NamedArgument | PositionalArgument, ...] = field(
        default_factory=tuple
    )
    allowed_flags: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def new_cmd_path(*parts: str) -> CommandPath:
        return parts

    def validate_definition(self) -> list[str]:
        errors: list[str] = []

        positional_positions: set[int] = set()
        named_names: set[str] = set()

        for argument in self.arguments:
            if isinstance(argument, PositionalArgument):
                if argument.position in positional_positions:
                    errors.append(
                        f"Duplicate positional argument index: {argument.position}"
                    )
                positional_positions.add(argument.position)

                if argument.position < 0:
                    errors.append(
                        f"Positional argument index cannot be negative: "
                        f"{argument.position}"
                    )

            elif isinstance(argument, NamedArgument):
                if argument.name in named_names:
                    errors.append(f"Duplicate named argument: {argument.name}")
                named_names.add(argument.name)

        return errors

    def is_allowed_flag(self, flag: str) -> bool:
        return flag in self.allowed_flags

    def is_allowed_arg_name(self, arg_name: str) -> bool:
        for arg in self.arguments:
            if isinstance(arg, NamedArgument):
                if arg.name == arg_name:
                    return True
        return False

    def is_allowed_arg_position(self, position: int) -> bool:
        for arg in self.arguments:
            if isinstance(arg, PositionalArgument):
                if arg.position == position:
                    return True
        return False

    def get_validator_for_argument(self, arg_name: str) -> ArgumentValidator | None:
        for arg in self.arguments:
            if isinstance(arg, NamedArgument):
                if arg.name == arg_name:
                    return arg.validator
        return

    def get_validator_for_pos_argument(self, position: int) -> ArgumentValidator | None:
        for arg in self.arguments:
            if isinstance(arg, PositionalArgument):
                if arg.position == position:
                    return arg.validator
        return


class CommandPack:
    def __init__(self, id: str | None = None) -> None:
        self.pack_id = id if id != None else str(uuid4())
        self.__commands: dict[CommandPath, Command] = {}
        self.__contained_pack_ids: dict[str, CommandPack] = {}
        self.__locked = False

    @property
    def commands(self) -> Mapping[CommandPath, Command]:
        return MappingProxyType(self.__commands)

    def get_command(self, cmd_path: CommandPath) -> Command | None:
        return self.commands.get(cmd_path)

    def exists(self, cmd_path: CommandPath) -> bool:
        return self.get_command(cmd_path) != None

    def __reg_validate_command(self, command: Command) -> tuple[bool, str]:
        cmd_path = command.cmd_path
        errors = command.validate_definition()

        if self.exists(cmd_path):
            msg = f"Unable to register command. Path already was registered: {cmd_path} | Pack ID: {self.pack_id}"
            return (False, msg)
        elif len(errors) != 0:
            msg = (
                f"Unable to register command with path {cmd_path}. Errors in command definition were detected: "
                + "\n\t".join(errors)
                + f"\n| Pack ID: {self.pack_id}"
            )
            return (False, msg)
        else:
            return (True, "")

    def register(self, command: Command) -> tuple[bool, str]:
        if self.__locked:
            raise RuntimeError(
                f"Pack with id {self.pack_id} is locked. No commands must be registered or unregistered."
            )

        success, msg = self.__reg_validate_command(command)
        if success:
            self.__commands[command.cmd_path] = command
        else:
            print(msg)

        return success, msg

    def unregister(self, command: Command) -> bool:
        if self.__locked:
            raise RuntimeError(
                f"Pack with id {self.pack_id} is locked. No commands must be registered or unregistered."
            )

        cmd_path = command.cmd_path
        if self.exists(cmd_path):
            self.__commands.pop(cmd_path, None)

            return True
        else:
            print(
                f"Unable to remove command with path: {cmd_path}. It is not in the pack. | Pack ID: {self.pack_id}"
            )

            return False

    def merge_from(self, other: CommandPack) -> bool:
        already_exists = self.__contained_pack_ids.get(other.pack_id, None) != None
        if already_exists:
            print(
                f"Unable to merge PackID: {other.pack_id} into PackID:{self.pack_id} because it was already merged."
            )
            return False

        command_pairs = other.commands.items()
        commands = []

        can_merge = True
        conflicts: list[tuple[CommandPath, str]] = []

        for cmd_pair in command_pairs:
            command = cmd_pair[1]
            success, msg = self.__reg_validate_command(command)
            commands.append(command)

            if not success:
                if can_merge:
                    can_merge = False
                conflicts.append((command.cmd_path, msg))

        if can_merge:
            for cmd in commands:
                self.register(cmd)

            self.__contained_pack_ids[other.pack_id] = other
            other.__locked = True
            return True
        else:
            print(
                f"Unable to merge PackID:{other.pack_id} into PackID:{self.pack_id} due to following conflicts:"
            )
            for conflict in conflicts:
                print(f"Command Path: {conflict[0]}")
                print("Conflict Message: ")
                print(conflict[1])
                print()

            return False

    def merge_into(self, other: CommandPack) -> bool:
        return other.merge_from(self)

    def detach_pack(self, other: CommandPack) -> bool:
        if other.pack_id in self.__contained_pack_ids.keys():
            command_pairs = other.commands.items()

            for command_pair in command_pairs:
                command = command_pair[1]
                self.unregister(command)

            self.__contained_pack_ids.pop(other.pack_id, None)
            other.__locked = False
            return True
        else:
            print(
                f"Unable to detach PackID:{other.pack_id} from PackID:{self.pack_id} , {other.pack_id} was not merged into {self.pack_id}"
            )
            return False


class CommandTokenType(Enum):
    WORD = auto()  # intermediate between PATH and VALUE
    PATH = auto()
    VALUE = auto()
    MULTI_WORD_FLAG = auto()
    SINGLE_CHAR_FLAG = auto()
    ARG_NAME = auto()
    ERROR = auto()


class CommandToken:
    def __init__(self, token_type: CommandTokenType, val: str) -> None:
        self.token_type = token_type
        self.value = val

    def change_token_type(self, new: CommandTokenType):
        self.token_type = new

    def set_value(self, val: str):
        self.value = val


class CommandParser:
    def __init__(self, check_cmd_exists: Callable[[tuple[str, ...]], bool]) -> None:
        self.check_cmd_exists = check_cmd_exists
        return

    def __tokenize_raw(self, raw_command: str) -> list[CommandToken]:
        raw_tokens = re.findall(r'"[^"]*"|\S+', raw_command)
        tokens = []

        for raw_token in raw_tokens:
            if raw_token.startswith('"') and raw_token.endswith('"'):
                # Remove only the surrounding quotes; preserve inner spaces.
                value = raw_token[1:-1]
                tokens.append(CommandToken(CommandTokenType.VALUE, value))
            elif raw_token.startswith("--"):
                tokens.append(CommandToken(CommandTokenType.ARG_NAME, raw_token[2:]))
            elif raw_token.startswith("-"):
                tokens.append(
                    CommandToken(CommandTokenType.MULTI_WORD_FLAG, raw_token[1:])
                )
            elif raw_token.startswith("/"):
                tokens.append(
                    CommandToken(CommandTokenType.SINGLE_CHAR_FLAG, raw_token[1:])
                )
            else:
                tokens.append(CommandToken(CommandTokenType.WORD, raw_token))

        return tokens

    def __split_single_char_flags(
        self, tokens: list[CommandToken]
    ) -> list[CommandToken]:
        split_tokens = []

        for token in tokens:
            if (
                token.token_type == CommandTokenType.SINGLE_CHAR_FLAG
                and len(token.value) > 1
            ):
                for char in token.value:
                    split_tokens.append(
                        CommandToken(CommandTokenType.SINGLE_CHAR_FLAG, char)
                    )
            else:
                split_tokens.append(token)

        return split_tokens

    def parse_raw(self, raw_command: str) -> list[CommandToken]:
        tokens = self.__tokenize_raw(raw_command)

        # Identify the longest valid command path.
        first_words = []

        for token in tokens:
            if token.token_type != CommandTokenType.WORD:
                break

            first_words.append(token.value)

        word_counter = 0
        path_attempt = []
        longest_match_length = 0

        for word in first_words:
            path_attempt.append(word)

            if self.check_cmd_exists(tuple(path_attempt)):
                longest_match_length = len(path_attempt)

        # Relabel the longest matching prefix as PATH.
        for i in range(longest_match_length):
            tokens[i].change_token_type(CommandTokenType.PATH)

        # identify other values
        for token in tokens:
            if token.token_type == CommandTokenType.WORD:
                token.token_type = CommandTokenType.VALUE

        return self.__split_single_char_flags(tokens)


class CommandManager:
    def __init__(self) -> None:
        self.main_pack = CommandPack("__main_cmd_pack__")
        self.__contains_packs: dict[str, CommandPack] = {}
        self.__parser = CommandParser(self.command_path_exists)

    def register_pack(self, pack: CommandPack) -> bool:
        success = self.main_pack.merge_from(pack)
        if success:
            self.__contains_packs[pack.pack_id] = pack
        return success

    def unregister_pack(self, pack_id: str) -> bool:
        other_pack = self.__contains_packs.get(pack_id)

        if not other_pack:
            print(
                f"Unable to detach PackID:{pack_id} from Main Pack , {pack_id} was not registered in Main Pack"
            )
            return False

        success = self.main_pack.detach_pack(other_pack)
        if success:
            self.__contains_packs.pop(other_pack.pack_id, None)

        return success

    def get_command(self, cmd_path: CommandPath) -> Command | None:
        return self.main_pack.get_command(cmd_path)

    def command_path_exists(self, cmd_path: CommandPath):
        return self.main_pack.exists(cmd_path)

    def try_execute(self, raw_input: str) -> CmdExecutionResult:
        parsed_tokens = self.__parser.parse_raw(raw_input)

        # Construct path
        path = []
        for token in parsed_tokens:
            if token.token_type != CommandTokenType.PATH:
                break
            path.append(token.value)
        path = tuple(path)
        display_path = " ".join(path)

        if len(path) == 0:
            return CmdExecutionResult(
                CmdExecutionCode.Error, "Cannot identify provided command: " + raw_input
            )

        pos_arguments: list[str] = []
        named_arguments: dict[str, str] = {}
        flags: list = []

        # collect arguments and flags
        counter = 0
        named_arg = False
        current_name = ""
        for token in parsed_tokens:
            if not named_arg and token.token_type == CommandTokenType.VALUE:
                pos_arguments.append(token.value)
            elif named_arg and token.token_type == CommandTokenType.VALUE:
                if current_name in named_arguments:
                    return CmdExecutionResult(
                        CmdExecutionCode.Error,
                        f"Argument '{current_name}' was provided more than once.",
                    )

                named_arguments[current_name] = token.value
                named_arg = False
                current_name = ""

            if named_arg and token.token_type != CommandTokenType.VALUE:
                return CmdExecutionResult(
                    CmdExecutionCode.Error,
                    f"No value was provided after argument name: {current_name}.",
                )

            if token.token_type == CommandTokenType.ARG_NAME:
                named_arg = True
                current_name = token.value

            if (
                token.token_type == CommandTokenType.MULTI_WORD_FLAG
                or token.token_type == CommandTokenType.SINGLE_CHAR_FLAG
            ):
                flags.append(token.value)
            counter += 1

        if named_arg:
            return CmdExecutionResult(
                CmdExecutionCode.Error,
                f"No value was provided after argument name: {current_name}.",
            )

        # perform validity checks
        command_description = self.get_command(path)

        if not command_description:
            return CmdExecutionResult(
                CmdExecutionCode.Error,
                f"No valid command description wad found for command with path: {display_path}",
            )

        # check whether all flags are allowed
        for flag in flags:
            if not command_description.is_allowed_flag(flag):
                return CmdExecutionResult(
                    CmdExecutionCode.Error,
                    f"Flag {flag} was not defined in command description for command: {display_path}",
                )

        # check whether all argument names and numbers are allowed
        for arg_name in named_arguments.keys():
            if not command_description.is_allowed_arg_name(arg_name):
                return CmdExecutionResult(
                    CmdExecutionCode.Error,
                    f"Argument name '{arg_name}' was not defined in command description for command: {display_path}",
                )

            validator = command_description.get_validator_for_argument(arg_name)

            if validator:
                success, err = validator(named_arguments[arg_name])
                if not success and err:
                    return CmdExecutionResult(
                        CmdExecutionCode.Error,
                        f"Argument Error caught while validating argument with name {arg_name} : {err.message} | Help: {err.help}",
                    )

        # same for positional arguments
        for pos, value in enumerate(pos_arguments):
            if not command_description.is_allowed_arg_position(pos):
                return CmdExecutionResult(
                    CmdExecutionCode.Error,
                    f"Received unexpected positional argument with value: '{value} | For command: {display_path}",
                )

            validator = command_description.get_validator_for_pos_argument(pos)

            if validator:
                success, err = validator(pos_arguments[pos])
                if not success and err:
                    return CmdExecutionResult(
                        CmdExecutionCode.Error,
                        f"Argument Error caught while validating argument at position {pos} : {err.message} | Help: {err.help}",
                    )

        # construct unified argument table
        arguments: dict[str, str] = {}

        for i, arg in enumerate(pos_arguments):
            arguments[str(i)] = arg

        arguments = arguments | named_arguments

        # validate that all required arguments exist
        for arg in command_description.arguments:
            if isinstance(arg, NamedArgument):
                if arg.required:
                    if not arg.name in arguments.keys():
                        return CmdExecutionResult(
                            CmdExecutionCode.Error,
                            f"No required argument with name {arg.name} was provided.",
                        )
            elif isinstance(arg, PositionalArgument):
                if arguments.get(str(arg.position)) is None:
                    return CmdExecutionResult(
                        CmdExecutionCode.Error,
                        f"No required argument at position {arg.position} was provided.",
                    )

        # execute
        try:
            return command_description.handler(arguments, flags)
        except Exception as e:
            return CmdExecutionResult(
                CmdExecutionCode.Error,
                f"Unexpected error occurred while executing command: {raw_input}. Error: {e}",
            )


# TODO: API design
# TODO: write tests

# TEMP:

some_central_manager = CommandManager()
my_commands = CommandPack(
    "my_commands"
)  # this is done at core of the program and in every plugin which wants to add commands


def my_cmd_handler(args: ArgDict, flags: AppliedFlags) -> CmdExecutionResult:
    print(f"COOL: {args["coolness"]}")

    if "r" in flags:
        print("R!")

    if "s" in flags:
        print("S!")

    return CmdExecutionResult(CmdExecutionCode.Success)


def my_cool_validator(arg: str) -> tuple[bool, ArgumentError | None]:
    try:
        converted = int(arg)
        if converted <= 0 or converted > 10:
            return False, ArgumentError(
                "The argument must be greater than 0 and less or equal to 10",
                "Correct argument's range.",
            )
    except:
        return False, ArgumentError(
            "The argument must be an integer!",
            "Consider checking it for non-numeric characters.",
        )

    return True, None


import os
import subprocess


def clear_console(args: ArgDict, flags: AppliedFlags) -> CmdExecutionResult:
    # Use 'cls' for Windows, 'clear' for Linux/macOS
    command = "cls" if os.name == "nt" else "clear"
    subprocess.call(command, shell=True)
    return CmdExecutionResult(CmdExecutionCode.Success)


my_commands.register(
    Command(
        cmd_path=("my", "cmd"),
        handler=my_cmd_handler,
        description="description",
        arguments=(
            NamedArgument(
                name="coolness",
                required=True,
                validator=my_cool_validator,
            ),
        ),
        allowed_flags=("r", "s"),
    )
)

my_commands.register(Command(cmd_path=("cls",), handler=clear_console))

some_central_manager.register_pack(my_commands)

while True:
    cmd = input("> ")
    if cmd == "quit":
        break

    print("Executing: ", cmd)
    res = some_central_manager.try_execute(cmd)
    print("Execution Status:", res.cmd_execution_code.name)
    print("Execution Return Value:", res.value)
    print()
