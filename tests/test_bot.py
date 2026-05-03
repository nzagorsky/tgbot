from tgbot.__main__ import build_app


def test_build_app_registers_basic_commands() -> None:
    app = build_app("123:ABC")

    commands = set()
    for handler in app.handlers[0]:
        commands.update(handler.commands)

    assert {"start", "hello", "help"} <= commands
