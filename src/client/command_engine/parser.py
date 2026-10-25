import re
from collections.abc import Callable
from definitions import CommandPath, CommandToken, CommandTokenType

# ---------------------------------------------------------------------------
# Tokenisation and command parsing
# ---------------------------------------------------------------------------


class CommandParser:
    _TOKEN_PATTERN = re.compile(r'"([^"]*)"|(\S+)')

    def __init__(self, check_cmd_exists: Callable[[CommandPath], bool]) -> None:
        self.__check_cmd_exists = check_cmd_exists

    def __tokenize_raw(self, raw_command: str) -> list[CommandToken]:
        tokens: list[CommandToken] = []

        for match in self._TOKEN_PATTERN.finditer(raw_command):
            quoted_value, unquoted_value = match.groups()

            if quoted_value is not None:
                tokens.append(CommandToken(CommandTokenType.VALUE, quoted_value))
                continue

            value = unquoted_value
            if value.startswith("--"):
                tokens.append(CommandToken(CommandTokenType.ARG_NAME, value[2:]))
            elif value.startswith("-"):
                tokens.append(CommandToken(CommandTokenType.MULTI_WORD_FLAG, value[1:]))
            elif value.startswith("/"):
                tokens.append(
                    CommandToken(CommandTokenType.SINGLE_CHAR_FLAG, value[1:])
                )
            else:
                tokens.append(CommandToken(CommandTokenType.WORD, value))

        return tokens

    @staticmethod
    def __split_single_char_flags(
        tokens: list[CommandToken],
    ) -> list[CommandToken]:
        split_tokens: list[CommandToken] = []

        for token in tokens:
            if (
                token.token_type is CommandTokenType.SINGLE_CHAR_FLAG
                and len(token.value) > 1
            ):
                split_tokens.extend(
                    CommandToken(CommandTokenType.SINGLE_CHAR_FLAG, char)
                    for char in token.value
                )
            else:
                split_tokens.append(token)

        return split_tokens

    def __resolve_command_path(self, tokens: list[CommandToken]) -> None:
        first_words: list[str] = []

        for token in tokens:
            if token.token_type is not CommandTokenType.WORD:
                break
            first_words.append(token.value)

        longest_match = 0
        path_parts: list[str] = []

        for word in first_words:
            path_parts.append(word)
            if self.__check_cmd_exists(tuple(path_parts)):
                longest_match = len(path_parts)

        for token in tokens[:longest_match]:
            token.token_type = CommandTokenType.PATH

        for token in tokens:
            if token.token_type is CommandTokenType.WORD:
                token.token_type = CommandTokenType.VALUE

    def parse_raw(self, raw_command: str) -> list[CommandToken]:
        tokens = self.__tokenize_raw(raw_command)
        self.__resolve_command_path(tokens)
        return self.__split_single_char_flags(tokens)
