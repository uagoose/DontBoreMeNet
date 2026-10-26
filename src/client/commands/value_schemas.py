from .definitions import *


class SanitizerTemplates:
    @staticmethod
    def Default() -> ArgumentSanitizer:
        return str.strip


class ValidatorTemplates:
    @staticmethod
    def Default() -> ArgumentValidator:
        def default(val: str) -> tuple[bool, ArgumentError | None]:
            return True, None

        return default

    @staticmethod
    def Integer(min_: int | None = None, max_: int | None = None) -> ArgumentValidator:
        def integer_validator(val: str):
            try:
                converted = int(val)
                if min_ is not None:
                    if converted < min_:
                        return False, ArgumentError(
                            f"Provided argument must be greater than {min_} | {val} was provided.",
                            "Provide bigger number.",
                        )
                if max_ is not None:
                    if converted > max_:
                        return False, ArgumentError(
                            f"Provided argument must be less than {max_} | {val} was provided.",
                            "Provide smaller number.",
                        )
            except Exception:
                return False, ArgumentError(
                    "Provided argument must be an integer.",
                    "Remove any non-integer symbols.",
                )

            return True, None

        return integer_validator


class ConverterTemplates:
    @staticmethod
    def Integer() -> ArgumentConverter:
        return int


class SchemaTemplates:
    @staticmethod
    def Default() -> ValueSchema:
        return ValueSchema(ValidatorTemplates.Default())

    @staticmethod
    def DefaultStripped() -> ValueSchema:
        return ValueSchema(ValidatorTemplates.Default(), SanitizerTemplates.Default())

    @staticmethod
    def Integer(
        min_: int | None = None,
        max_: int | None = None,
    ) -> ValueSchema:
        return ValueSchema(
            ValidatorTemplates.Integer(min_, max_),
            SanitizerTemplates.Default(),
            ConverterTemplates.Integer(),
        )
