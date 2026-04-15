# banner.py
# Terminal banner, footer, and shared box-drawing utilities for H2LaserDAQ.
#
# Public box helpers (used by both this module and the TUI launcher):
#   box_top()           ╔══...══╗
#   box_line(content)   ║ content (padded) ║
#   box_bottom()        ╚══...══╝
#   box_divider(label)  ╠══ label ══╣
#   header_section_lines()  → the identity header as a list of lines (open, no ╚)
#
# ANSI colours are applied only when stdout is a real TTY.

import re
import sys
from datetime import datetime

# ── Identity ──────────────────────────────────────────────────────────────────
_VERSION = "3"
_AUTHOR  = "Meng Lyu"
_INST    = "University of Tokyo"
_COPY    = "Since 2025"

# ── Box geometry ──────────────────────────────────────────────────────────────
BOX_INNER = 62   # visual character width between the two ║ borders

# ── ANSI palette (Catppuccin Mocha) ───────────────────────────────────────────
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[96m"
_YELLOW = "\033[93m"
_GREEN  = "\033[92m"
_RESET  = "\033[0m"


def _c(code: str, text: str) -> str:
    """Apply ANSI code only when stdout is a real TTY."""
    return f"{code}{text}{_RESET}" if sys.stdout.isatty() else text


def vis_len(s: str) -> int:
    """Visual length of a string, ignoring ANSI escape sequences."""
    return len(re.sub(r"\x1b\[[0-9;]*m", "", s))


# ── Box-drawing helpers (public — also used by the TUI launcher) ──────────────

def box_top() -> str:
    return f"  ╔{'═' * BOX_INNER}╗"


def box_bottom() -> str:
    return f"  ╚{'═' * BOX_INNER}╝"


def box_line(content: str = "") -> str:
    """One bordered content line: ║ content (padded to BOX_INNER) ║"""
    pad = max(0, BOX_INNER - vis_len(content))
    return f"  ║{content}{' ' * pad}║"


def box_divider(label: str = "") -> str:
    """╠══ label ══╣  — label may contain ANSI codes; padding uses visual width."""
    if not label:
        return f"  ╠{'═' * BOX_INNER}╣"
    vis   = vis_len(label)
    pad   = BOX_INNER - vis
    left  = pad // 2
    right = pad - left
    return f"  ╠{'═' * left}{label}{'═' * right}╣"


# ── Shared identity header ────────────────────────────────────────────────────

def header_section_lines() -> list:
    """
    Return the identity header as a list of lines: from ╔ down to (and
    including) the last blank ║ line, but WITHOUT a closing ╚.

    The caller appends a ╠ divider, menu content, and a ╚ to complete the box.
    This is the single source of truth for the header used in both
    print_banner() and the TUI launcher.
    """
    title_plain   = "    H2 LASER  D A Q"
    version_plain = f"v{_VERSION}  "
    gap           = BOX_INNER - len(title_plain) - len(version_plain)
    title_line    = (
        "    "
        + _c(_BOLD + _CYAN, "H2 LASER  D A Q")
        + " " * gap
        + _c(_YELLOW, f"v{_VERSION}")
        + "  "
    )
    return [
        box_top(),
        box_line(),
        box_line(title_line),
        box_line("    " + _c(_DIM, "Data Acquisition System for H2 Laser Experiments")),
        box_line("    " + _c(_DIM, f"{_AUTHOR}  ·  {_INST}  ·  {_COPY}")),
        box_line(),
    ]


# ── Duration formatting ───────────────────────────────────────────────────────

_start_time: datetime | None = None


def _fmt_duration(seconds: float) -> str:
    s = int(seconds)
    if s < 60:
        return f"{s} s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h {m:02d}m"


# ── Public API ────────────────────────────────────────────────────────────────

def print_banner(subtitle: str) -> None:
    """
    Print the opening banner.

        ╔══════════════════════════════════════════════════════════════╗
        ║                                                              ║
        ║    H2 LASER  D A Q                                  v3      ║
        ║    Data Acquisition System for H2 Laser                      ║
        ║    Meng Lyu  ·  University of Tokyo  ·  Since 2025           ║
        ║                                                              ║
        ╠══════════════════════ ◆  Session  ◆ ═════════════════════════╣
        ║                                                              ║
        ║    ▸  <subtitle>                                             ║
        ║    ▸  Started  ·  YYYY/MM/DD  HH:MM:SS                      ║
        ║                                                              ║
        ╚══════════════════════════════════════════════════════════════╝
    """
    global _start_time
    _start_time = datetime.now()
    ts = _start_time.strftime("%Y/%m/%d  %H:%M:%S")

    session_label = "  " + _c(_GREEN, "◆  Session  ◆") + "  "

    lines = header_section_lines()
    lines += [
        box_divider(session_label),
        box_line(),
        box_line("    " + _c(_GREEN, "▸") + "  " + _c(_BOLD, subtitle)),
        box_line("    " + _c(_GREEN, "▸") + "  " + _c(_DIM, "Started") + "  ·  " + ts),
        box_line(),
        box_bottom(),
        "",
    ]
    print()
    print("\n".join(lines))


def print_footer(subtitle: str) -> None:
    """
    Print the shutdown footer with elapsed duration.

        ╔══════════════════════════════════════════════════════════════╗
        ║    ✓  <subtitle>  ·  ended normally                          ║
        ║       Stopped  ·  YYYY/MM/DD  HH:MM:SS  ·  Duration: Xm XXs ║
        ╚══════════════════════════════════════════════════════════════╝
    """
    now      = datetime.now()
    ts       = now.strftime("%Y/%m/%d  %H:%M:%S")
    duration = _fmt_duration((now - _start_time).total_seconds()) if _start_time else "—"

    ended_line = (
        "    "
        + _c(_GREEN, "✓")
        + "  "
        + _c(_BOLD, subtitle)
        + _c(_DIM, "  ·  ended normally")
    )
    time_line = (
        "       "
        + _c(_DIM, "Stopped")
        + "  ·  "
        + ts
        + "  ·  "
        + _c(_DIM, "Duration")
        + ": "
        + _c(_YELLOW, duration)
    )

    lines = [
        "",
        box_top(),
        box_line(ended_line),
        box_line(time_line),
        box_bottom(),
        "",
    ]
    print("\n".join(lines))
