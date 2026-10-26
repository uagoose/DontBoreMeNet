from collections.abc import Mapping
from types import MappingProxyType
from uuid import uuid4
from .definitions import *
from .__parser import CommandParser

# ---------------------------------------------------------------------------
# Command packs
# ---------------------------------------------------------------------------


class CommandPack:
    def __init__(self, pack_id: str | None = None) -> None:
        self.pack_id = pack_id if pack_id is not None else str(uuid4())
        self.__commands: dict[CommandPath, Command] = {}
        self.__contained_packs: dict[str, CommandPack] = {}
        self.__locked = False

    @property
    def commands(self) -> Mapping[CommandPath, Command]:
        return MappingProxyType(self.__commands)

    @property
    def is_locked(self) -> bool:
        return self.__locked

    def get_command(self, cmd_path: CommandPath) -> Command | None:
        return self.__commands.get(cmd_path)

    def exists(self, cmd_path: CommandPath) -> bool:
        return cmd_path in self.__commands

    def __ensure_unlocked(self) -> None:
        if self.__locked:
            raise RuntimeError(
                f"Command pack {self.pack_id!r} is locked because it is merged "
                "into another pack."
            )

    def __validate_registration(self, command: Command) -> list[str]:
        errors = command.validate_definition()

        if self.exists(command.cmd_path):
            errors.insert(0, f"Command path already registered: {command.cmd_path}")

        return errors

    def register(self, command: Command) -> tuple[bool, str]:
        self.__ensure_unlocked()

        errors = self.__validate_registration(command)
        if errors:
            message = self.__format_errors(
                f"Unable to register command {command.cmd_path}", errors
            )
            print(message)
            return False, message

        self.__commands[command.cmd_path] = command
        return True, ""

    def unregister(self, command: Command) -> bool:
        self.__ensure_unlocked()

        registered = self.__commands.get(command.cmd_path)
        if registered is not command:
            print(
                f"Unable to unregister {command.cmd_path}: the exact command "
                f"is not registered in pack {self.pack_id}."
            )
            return False

        del self.__commands[command.cmd_path]
        return True

    def merge_from(self, other: CommandPack) -> bool:
        if other is self:
            print("A command pack cannot be merged into itself.")
            return False

        if self.__locked:
            raise RuntimeError(f"Command pack {self.pack_id!r} is locked.")

        if other.pack_id in self.__contained_packs:
            print(
                f"Pack {other.pack_id!r} has already been merged into "
                f"{self.pack_id!r}."
            )
            return False

        conflicts: list[str] = []
        for command in other.commands.values():
            conflicts.extend(self.__validate_registration(command))

        if conflicts:
            print(
                self.__format_errors(
                    f"Unable to merge pack {other.pack_id!r} into " f"{self.pack_id!r}",
                    conflicts,
                )
            )
            return False

        # Validate everything before mutating either pack.
        self.__commands.update(other.commands)
        self.__contained_packs[other.pack_id] = other
        other.__locked = True
        return True

    def merge_into(self, other: CommandPack) -> bool:
        return other.merge_from(self)

    def detach_pack(self, other: CommandPack) -> bool:
        if self.__locked:
            raise RuntimeError(f"Command pack {self.pack_id!r} is locked.")

        contained = self.__contained_packs.get(other.pack_id)
        if contained is not other:
            print(f"Pack {other.pack_id!r} is not merged into {self.pack_id!r}.")
            return False

        # Only remove commands that are still the same objects supplied by
        # the attached pack. Never remove a replacement registered at that path.
        for path, command in other.commands.items():
            if self.__commands.get(path) is command:
                del self.__commands[path]

        del self.__contained_packs[other.pack_id]
        other.__locked = False
        return True

    @staticmethod
    def __format_errors(title: str, errors: list[str]) -> str:
        details = "\n".join(f"  - {error}" for error in errors)
        return f"{title}:\n{details}"


# ---------------------------------------------------------------------------
# Command execution & Management
# ---------------------------------------------------------------------------


class CommandManager:
    def __init__(self) -> None:
        self.main_pack = CommandPack("__main_cmd_pack__")
        self.__registered_packs: dict[str, CommandPack] = {}
        self.__parser = CommandParser(self.command_path_exists)

    def register_pack(self, pack: CommandPack) -> bool:
        if pack.pack_id in self.__registered_packs:
            print(f"Pack {pack.pack_id!r} is already registered.")
            return False

        success = self.main_pack.merge_from(pack)
        if success:
            self.__registered_packs[pack.pack_id] = pack
        return success

    def unregister_pack(self, pack_id: str) -> bool:
        pack = self.__registered_packs.get(pack_id)
        if pack is None:
            print(f"Pack {pack_id!r} is not registered in the main pack.")
            return False

        if not self.main_pack.detach_pack(pack):
            return False

        del self.__registered_packs[pack_id]
        return True

    def get_command(self, cmd_path: CommandPath) -> Command | None:
        return self.main_pack.get_command(cmd_path)

    def command_path_exists(self, cmd_path: CommandPath) -> bool:
        return self.main_pack.exists(cmd_path)

    @staticmethod
    def __error(message: str) -> CommandExecutionResult:
        return CommandExecutionResult.error(message)

    def __collect_arguments(
        self, tokens: list[CommandToken], command_path: CommandPath
    ) -> tuple[list[str], ArgDict, AppliedFlags] | CommandExecutionResult:
        positional_values: list[str] = []
        named_values: ArgDict = {}
        flags: AppliedFlags = []
        named_argument_pending = False
        current_name = ""

        for token in tokens:
            if token.token_type in (CommandTokenType.PATH,):
                continue

            if token.token_type is CommandTokenType.ARG_NAME:
                if named_argument_pending:
                    return self.__error(
                        f"No value was provided after argument name: {current_name}."
                    )
                if not token.value:
                    return self.__error("Argument name cannot be empty.")

                named_argument_pending = True
                current_name = token.value
                continue

            if token.token_type in (
                CommandTokenType.MULTI_WORD_FLAG,
                CommandTokenType.SINGLE_CHAR_FLAG,
            ):
                if named_argument_pending:
                    return self.__error(
                        f"No value was provided after argument name: {current_name}."
                    )
                flags.append(token.value)
                continue

            if token.token_type is CommandTokenType.VALUE:
                if named_argument_pending:
                    if current_name in named_values:
                        return self.__error(
                            f"Argument {current_name!r} was provided more than once."
                        )
                    named_values[current_name] = token.value
                    named_argument_pending = False
                    current_name = ""
                else:
                    positional_values.append(token.value)

        if named_argument_pending:
            return self.__error(
                f"No value was provided after argument name: {current_name}."
            )

        return positional_values, named_values, flags

    def __validate_arguments(
        self,
        command: Command,
        positional_values: list[str],
        named_values: ArgDict,
        flags: AppliedFlags,
        display_path: str,
    ) -> CommandExecutionResult | None:
        for flag in flags:
            if not command.is_allowed_flag(flag):
                return self.__error(
                    f"Flag {flag!r} was not defined for command: {display_path}"
                )

        for name, value in named_values.items():
            argument = command.get_named_argument(name)
            if argument is None:
                return self.__error(
                    f"Argument name {name!r} was not defined for command: "
                    f"{display_path}"
                )

            schema = argument.schema
            sanitized = schema.sanitizer(value)
            valid, error = schema.validator(sanitized)
            if not valid:
                if error is None:
                    return self.__error(
                        f"Validator rejected argument {name!r} without an error."
                    )
                return self.__error(
                    f"Argument error for {name!r}: {error.message} | "
                    f"Help: {error.help}"
                )

            new_value = schema.converter(sanitized)
            named_values[name] = new_value

        for position, value in enumerate(positional_values):
            argument = command.get_positional_argument(position)
            if argument is None:
                return self.__error(
                    f"Unexpected positional argument {value!r} for command: "
                    f"{display_path}"
                )

            schema = argument.schema
            sanitized = schema.sanitizer(value)
            valid, error = schema.validator(sanitized)
            if not valid:
                if error is None:
                    return self.__error(
                        f"Validator rejected positional argument {position} "
                        "without an error."
                    )
                return self.__error(
                    f"Argument error at position {position}: {error.message} | "
                    f"Help: {error.help}"
                )

            new_value = schema.converter(sanitized)
            positional_values[position] = new_value

        for argument in command.arguments:
            if isinstance(argument, NamedArgument):
                if argument.required and argument.name not in named_values:
                    return self.__error(
                        f"No required argument with name {argument.name} was provided."
                    )
            elif isinstance(argument, PositionalArgument):
                if argument.position >= len(positional_values):
                    return self.__error(
                        f"No required argument at position {argument.position} "
                        "was provided."
                    )

        return None

    def try_execute(self, raw_input: str) -> CommandExecutionResult:
        tokens = self.__parser.parse_raw(raw_input)

        command_path: CommandPath = tuple(
            token.value for token in tokens if token.token_type is CommandTokenType.PATH
        )
        if not command_path:
            return self.__error(f"Cannot identify provided command: {raw_input}")

        command = self.get_command(command_path)
        if command is None:
            display_path = " ".join(command_path)
            return self.__error(
                f"No command definition was found for path: {display_path}"
            )

        collected = self.__collect_arguments(tokens, command_path)
        if isinstance(collected, CommandExecutionResult):
            return collected

        positional_values, named_values, flags = collected
        display_path = " ".join(command_path)

        validation_error = self.__validate_arguments(
            command,
            positional_values,
            named_values,
            flags,
            display_path,
        )
        if validation_error is not None:
            return validation_error

        arguments: ArgDict = {
            str(position): value for position, value in enumerate(positional_values)
        }
        arguments.update(named_values)

        try:
            return command.handler(arguments, flags)
        except Exception as exc:
            return self.__error(
                f"Unexpected error while executing command {raw_input!r}: {exc}"
            )
