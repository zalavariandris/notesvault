"""Entry point for the console executable; retain --once and --check modes."""
from notesvault.__main__ import main


if __name__ == "__main__":
    main(default_tui=True)
