"""Interactive CLI shell boundary for APCOS."""

from __future__ import annotations

from typing import Callable

from interface.interaction_controller import InteractionController

HELP_TEXT = (
    "Commands:\n"
    "  login owner|family|guest [user_id]\n"
    "  schedule meeting tomorrow at 10\n"
    "  mark <task> completed\n"
    "  cancel task <task>\n"
    "  /strategy <question>\n"
    "  help\n"
    "  exit"
)


def run_shell(
    controller: InteractionController,
    *,
    input_func: Callable[[str], str] = input,
    output_func: Callable[[str], None] = print,
) -> None:
    """Run interactive CLI loop."""
    output_func("APCOS CLI ready. Type 'help' for commands.")
    while True:
        try:
            user_input = input_func("apcos> ")
        except KeyboardInterrupt:
            output_func("\nSession interrupted. Exiting APCOS CLI.")
            return
        except EOFError:
            output_func("\nSession ended. Exiting APCOS CLI.")
            return

        command = (user_input or "").strip()
        lowered = command.lower()

        if lowered in {"exit", "quit"}:
            output_func("Exiting APCOS CLI.")
            return
        if lowered == "help":
            output_func(HELP_TEXT)
            continue
        if not command:
            output_func("Please enter a command.")
            continue

        try:
            response = controller.handle_input(command)
        except Exception:
            response = "I could not execute that due to an internal system error."
        output_func(response)


if __name__ == "__main__":
    raise SystemExit(
        "Use run_shell(controller=...) from your bootstrap entrypoint to start APCOS CLI."
    )
