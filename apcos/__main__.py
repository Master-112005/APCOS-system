"""Module entrypoint for running APCOS as `python -m apcos`."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Sequence

from apcos.bootstrap.config_loader import ConfigError, load_config
from apcos.bootstrap.container import build_app, build_real_voice_session, build_voice_session
from apcos.bootstrap.logging_config import configure_logging
from apcos.bootstrap.startup_validator import StartupValidationError, validate_startup
from interface.cli_shell import run_shell
from voice.voice_controller import run_voice_loop


def main(argv: Sequence[str] | None = None) -> int:
    """Run APCOS CLI entrypoint."""
    parser = argparse.ArgumentParser(prog="apcos", description="APCOS interactive cognitive shell")
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Path to APCOS YAML configuration file.",
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        help="Run APCOS in voice loop mode.",
    )
    parser.add_argument(
        "--voice-real",
        action="store_true",
        help="Run APCOS in real voice pipeline mode (Stage 7).",
    )
    parser.add_argument(
        "--runtime-governor",
        dest="runtime_governor",
        action="store_true",
        help="Enable runtime resource governor in real voice mode.",
    )
    parser.add_argument(
        "--no-runtime-governor",
        dest="runtime_governor",
        action="store_false",
        help="Disable runtime resource governor in real voice mode.",
    )
    parser.set_defaults(runtime_governor=None)
    args = parser.parse_args(argv)

    configure_logging()
    logger = logging.getLogger(__name__)

    try:
        config = load_config(args.config)
        project_root = Path(__file__).resolve().parents[1]
        validate_startup(config, project_root=project_root)
        if args.voice_real:
            runtime_governor_enabled = (
                True if args.runtime_governor is None else bool(args.runtime_governor)
            )
            session = build_real_voice_session(
                args.config,
                config=config,
                runtime_governor_enabled=runtime_governor_enabled,
            )
            run_voice_loop(session)
        elif args.voice:
            session = build_voice_session(args.config, config=config)
            run_voice_loop(session)
        else:
            controller = build_app(args.config, config=config)
            run_shell(controller)
        return 0
    except (ConfigError, StartupValidationError) as exc:
        logger.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
