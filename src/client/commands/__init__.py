from collections.abc import Callable
from typing import Any, TypeVar

from . import managers
from .definitions import (
    AppliedFlags,
    ArgDict,
    Command,
    CommandExecutionResult,
    NamedArgument,
    PositionalArgument,
    CommandHandler,
)

_METADATA_ATTR = "__dbm_commands_metadata__"


# ---------------------------------------------------------------------------
# Internal decorator metadata
# ---------------------------------------------------------------------------


class _CommandsMeta:
    def __init__(self) -> None:
        self.arguments: list[NamedArgument | PositionalArgument] = []
        self.flags: list[str] = []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class Commands:
    def __init__(self, pack_id: str | None = None) -> None:
        self.pack = managers.CommandPack(pack_id)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def __metadata_for(self, handler: CommandHandler) -> _CommandsMeta:
        # Keep metadata scoped to this Commands instance.
        # This prevents declarations from different packs mixing together.
        metadata_store = getattr(handler, _METADATA_ATTR, None)

        if metadata_store is None:
            metadata_store = {}
            setattr(handler, _METADATA_ATTR, metadata_store)

        instance_key = id(self)

        if instance_key not in metadata_store:
            metadata_store[instance_key] = _CommandsMeta()

        return metadata_store[instance_key]

    def __clear_metadata(self, handler: CommandHandler) -> None:
        metadata_store = getattr(handler, _METADATA_ATTR, None)

        if metadata_store is None:
            return

        metadata_store.pop(id(self), None)

        if not metadata_store:
            delattr(handler, _METADATA_ATTR)

    def __add_argument(
        self,
        argument: NamedArgument | PositionalArgument,
    ) -> Callable[[CommandHandler], CommandHandler]:

        def decorator(handler: CommandHandler) -> CommandHandler:
            metadata = self.__metadata_for(handler)

            # Decorators run bottom-up. Insert at the front to preserve
            # the declaration order written in the source code.
            metadata.arguments.insert(0, argument)

            return handler

        return decorator

    # -----------------------------------------------------------------------
    # Command declaration
    # -----------------------------------------------------------------------

    def command(
        self,
        *,
        path: str,
        description: str = "",
    ) -> Callable[[CommandHandler], CommandHandler]:

        def decorator(handler: CommandHandler) -> CommandHandler:
            metadata = self.__metadata_for(handler)

            try:
                command = Command(
                    cmd_path=tuple(path.strip().split(" ")),
                    handler=handler,
                    description=description,
                    arguments=tuple(metadata.arguments),
                    allowed_flags=tuple(metadata.flags),
                )

                success, message = self.pack.register(command)

                if not success:
                    raise ValueError(
                        message or f"Unable to register command at path {path!r}."
                    )

            finally:
                # Prevent stale declarations from affecting later uses
                # of the same function.
                self.__clear_metadata(handler)

            return handler

        return decorator

    # -----------------------------------------------------------------------
    # Argument declarations
    # -----------------------------------------------------------------------

    def positional(
        self,
        *,
        position: int,
        schema: Any,
    ) -> Callable[[CommandHandler], CommandHandler]:
        return self.__add_argument(
            PositionalArgument(
                position=position,
                schema=schema,
            )
        )

    def named(
        self,
        name: str,
        *,
        schema: Any,
        required: bool = True,
    ) -> Callable[[CommandHandler], CommandHandler]:
        return self.__add_argument(
            NamedArgument(
                name=name,
                schema=schema,
                required=required,
            )
        )

    # -----------------------------------------------------------------------
    # Flag declarations
    # -----------------------------------------------------------------------

    def flag(
        self,
        name: str,
    ) -> Callable[[CommandHandler], CommandHandler]:

        def decorator(handler: CommandHandler) -> CommandHandler:
            metadata = self.__metadata_for(handler)
            metadata.flags.insert(0, name)
            return handler

        return decorator
