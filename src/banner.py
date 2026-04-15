# banner.py
# Shared startup / shutdown banners for H2LaserDAQ runner scripts.
#
# ANSI colours are applied automatically when stdout is a real terminal;
# they are stripped when output is piped or redirected to a file.

import sys
from datetime import datetime

_VERSION = "3.0"
_AUTHOR  = "Meng Lyu"
_INST    = "University of Tokyo"
_YEARS   = "2025-2026"

# ANSI escape codes
_BOLD   = "\033[1m"
_CYAN   = "\033[96m"   # project name
_YELLOW = "\033[93m"   # version tag
_GREEN  = "\033[92m"   # bullet / info
_DIM    = "\033[2m"    # description / attribution
_RESET  = "\033[0m"

_RULE = "  " + "═" * 62


def _c(code: str, text: str) -> str:
    """Apply *code* around *text* only when stdout is a real TTY."""
    if sys.stdout.isatty():
        return f"{code}{text}{_RESET}"
    return text


def print_banner(subtitle: str) -> None:
    """
    Print the opening banner.

    Parameters
    ----------
    subtitle : str
        Short description of the running mode shown under the logo,
        e.g. ``"H2 VUV Photodiode  (snapshot mode)"``.
    """
    ts     = datetime.now().strftime("%Y/%m/%d  %H:%M:%S")
    bullet = _c(_GREEN, "▶")
    title  = (
        _c(_BOLD + _CYAN,  "H 2 L a s e r D A Q")
        + "   ·   "
        + _c(_YELLOW, f"v{_VERSION}")
    )
    desc   = _c(_DIM, "H2 Laser  ·  Data Acquisition System")
    auth   = _c(_DIM, f"{_AUTHOR}  ·  {_INST}  ·  {_YEARS}")

    print()
    print(_RULE)
    print()
    print(f"    {title}")
    print(f"    {desc}")
    print(f"    {auth}")
    print()
    print(f"    {bullet}  {subtitle}")
    print(f"    {bullet}  Started :  {ts}")
    print()
    print(_RULE)
    print()


def print_footer(subtitle: str) -> None:
    """Print the shutdown footer."""
    ts     = datetime.now().strftime("%Y/%m/%d  %H:%M:%S")
    bullet = _c(_GREEN, "▶")

    print()
    print(_RULE)
    print(f"    {bullet}  {subtitle} ended normally.")
    print(f"    {bullet}  Stopped :  {ts}")
    print(_RULE)
    print()
