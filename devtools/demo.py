"""Run synthetic data from a source checkout: python -m devtools.demo [--tui | --once]."""
import argparse
from collections.abc import Sequence
import logging

from notesvault.__main__ import run_gui, run_once, run_tui
from .synthetic import demo_application


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Try Notes Vault with disposable synthetic data.")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--tui", dest="mode", action="store_const", const="tui")
    modes.add_argument("--once", dest="mode", action="store_const", const="once")
    parser.set_defaults(mode="gui")
    args = parser.parse_args(argv)
    logging.disable(logging.CRITICAL)
    with demo_application() as application:
        match args.mode:
            case "gui":
                run_gui(application)
            case "tui":
                run_tui(application)
            case "once":
                run_once(application)


if __name__ == "__main__":
    main()
