from commands import Commands
from commands import managers
from commands import definitions
from commands.definitions import CommandExecutionResult, CommandExecutionCode
from commands.value_schemas import SchemaTemplates

command_manager = managers.CommandManager()

cmd = Commands("main")


@cmd.command(path="cmd")
@cmd.positional(position=0, schema=SchemaTemplates.Integer())
@cmd.named("test", schema=SchemaTemplates.Default(), required=False)
@cmd.flag("special")
def cmd_handler(args, flags):
    print(args)
    print(flags)
    return CommandExecutionResult(CommandExecutionCode.Success)


def main():
    command_manager.register_pack(cmd.pack)

    while True:
        user_cmd = input("> ")
        if user_cmd == "quit":
            break

        res = command_manager.try_execute(user_cmd)

        print(f"- Command: {user_cmd}")
        print("- Execution Code: " + res.cmd_execution_code.name)

        if res.cmd_execution_code != definitions.CommandExecutionCode.Success:
            print(f"- Details: \n\t{res.value}")
        else:
            if res.value is not None:
                print(f"- Return Value: {res.value}")

        print()


if __name__ == "__main__":
    main()
