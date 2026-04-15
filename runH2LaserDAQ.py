# runH2LaserDAQ.py
# Unified interactive launcher for H2LaserDAQ.
#
# Level 1 — choose a run mode:
#     Continuous DAQ  /  Snapshot Monitor  /  History Viewer
#
# Level 2 — choose a config from config/ that matches the selected mode.
#
# Usage:
#     python3 runH2LaserDAQ.py

import glob
import importlib
import os
import sys

# ─────────────────────────────────────────────────────────────────────────────
# Run-mode registry
# ─────────────────────────────────────────────────────────────────────────────

_MODES = [
    {
        "label":  "Continuous DAQ",
        "mode":   "continuous",
        "runner": "runners.run_continuous",
    },
    {
        "label":  "Snapshot Monitor",
        "mode":   "snapshot",
        "runner": "runners.run_snapshot",
    },
    {
        "label":  "History Viewer",
        "mode":   "history",
        "runner": "runners.run_history_viewer",
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Config discovery — scans config/*.py and categorises by run_mode
# ─────────────────────────────────────────────────────────────────────────────

def _discover_configs() -> list:
    """
    Return a list of dicts, one per usable config file::

        {
            "title":    str,    # CONFIG_TITLE from the module
            "mode":     str,    # "continuous", "snapshot", or "history"
            "filename": str,    # e.g. "config_H2PD.py"
            "data":     dict,   # DIGITIZER_CONFIGS or HISTORY_CONFIG
        }
    """
    results  = []
    cfg_dir  = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config")

    for path in sorted(glob.glob(os.path.join(cfg_dir, "*.py"))):
        basename = os.path.basename(path)
        if basename.startswith("__"):
            continue

        mod_name = "config." + basename[:-3]
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue

        title = getattr(mod, "CONFIG_TITLE", mod_name)

        if hasattr(mod, "DIGITIZER_CONFIGS"):
            data = mod.DIGITIZER_CONFIGS
            # Derive mode from the first device entry
            first = next(iter(data.values()), {})
            mode  = first.get("run_mode", "unknown")
            results.append({
                "title":    title,
                "mode":     mode,
                "filename": basename,
                "data":     data,
            })

        elif hasattr(mod, "HISTORY_CONFIG"):
            results.append({
                "title":    title,
                "mode":     "history",
                "filename": basename,
                "data":     mod.HISTORY_CONFIG,
            })

    return results

# ─────────────────────────────────────────────────────────────────────────────
# ANSI helpers  (same palette as src/banner.py)
# ─────────────────────────────────────────────────────────────────────────────

_IS_TTY = sys.stdout.isatty() and sys.stdin.isatty()

_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[96m"
_YELLOW = "\033[93m"
_GREEN  = "\033[92m"
_RESET  = "\033[0m"
_CLEAR  = "\033[2J\033[H"

_VERSION = "3"
_AUTHOR  = "Meng Lyu"
_INST    = "University of Tokyo"
_YEARS   = "2025-2026"
_RULE    = "  " + "═" * 62


def _c(code: str, text: str) -> str:
    return f"{code}{text}{_RESET}" if _IS_TTY else text


# ─────────────────────────────────────────────────────────────────────────────
# TUI renderer
# ─────────────────────────────────────────────────────────────────────────────

_COL_LABEL  = 32   # left column width for menu items
_COL_DETAIL = 28   # right column width for detail text


def _render(section: str, items: list, selected: int) -> None:
    """
    Render the full screen.

    Parameters
    ----------
    section : str
        Prompt shown above the item list, e.g. "Select a mode:".
    items : list of (label, detail) or plain str
        Menu entries.  Use ``None`` as a visual separator (non-selectable).
    selected : int
        Index of the currently highlighted entry.
    """
    lines = []

    # ── header ────────────────────────────────────────────────────────────────
    lines.append("")
    lines.append(_RULE)
    lines.append("")
    lines.append(
        "    "
        + _c(_BOLD + _CYAN, "H 2 L a s e r D A Q")
        + "   ·   "
        + _c(_YELLOW, f"v{_VERSION}")
    )
    lines.append("    " + _c(_DIM, "H2 Laser  ·  Data Acquisition System"))
    lines.append("    " + _c(_DIM, f"{_AUTHOR}  ·  {_INST}  ·  {_YEARS}"))
    lines.append("")
    lines.append(_RULE)
    lines.append("")

    # ── section prompt ────────────────────────────────────────────────────────
    lines.append("    " + _c(_BOLD, section))
    lines.append("")

    # ── items ─────────────────────────────────────────────────────────────────
    for i, entry in enumerate(items):
        if entry is None:                          # visual separator
            lines.append("    " + _c(_DIM, "  ─" * 20))
            continue

        if isinstance(entry, tuple):
            label, detail = entry
        else:
            label, detail = entry, ""

        if i == selected:
            marker    = _c(_GREEN + _BOLD, " ❯ ")
            lbl_fmt   = _c(_BOLD + _CYAN, label.ljust(_COL_LABEL))
            det_fmt   = _c(_DIM, detail)
        else:
            marker    = "   "
            lbl_fmt   = _c(_DIM, label.ljust(_COL_LABEL))
            det_fmt   = _c(_DIM, detail)

        lines.append(f"  {marker} {lbl_fmt}  {det_fmt}")

    # ── footer hint ───────────────────────────────────────────────────────────
    lines.append("")
    lines.append(
        "    " + _c(_DIM, "↑ / ↓  navigate    Enter  confirm    q  quit")
    )
    lines.append("")
    lines.append(_RULE)
    lines.append("")

    if _IS_TTY:
        sys.stdout.write(_CLEAR)
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Key input
# ─────────────────────────────────────────────────────────────────────────────

try:
    import termios
    import tty
    _HAS_TERMIOS = True
except ImportError:
    _HAS_TERMIOS = False


def _getch() -> str:
    fd  = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            seq = sys.stdin.read(2)
            if seq == "[A":
                return "up"
            if seq == "[B":
                return "down"
            return "esc"
        if ch in ("\r", "\n"):
            return "enter"
        if ch == "\x03":
            raise KeyboardInterrupt
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _selectable_indices(items: list) -> list:
    """Return indices of items that are not separators (None)."""
    return [i for i, it in enumerate(items) if it is not None]


def _menu_select(section: str, items: list) -> int | None:
    """
    Display an arrow-key menu and return the index of the chosen item,
    or None if the user pressed q.

    Separator entries (None) are skipped during navigation.
    """
    sel_idx  = _selectable_indices(items)
    cursor   = 0   # position within sel_idx

    while True:
        _render(section, items, sel_idx[cursor])
        key = _getch()

        if key == "up":
            cursor = (cursor - 1) % len(sel_idx)
        elif key == "down":
            cursor = (cursor + 1) % len(sel_idx)
        elif key == "enter":
            return sel_idx[cursor]
        elif key in ("q", "Q"):
            return None


def _fallback_select(section: str, items: list) -> int | None:
    """Numbered fallback when stdin is not a TTY."""
    _render(section, items, 0)
    selectable = [(i, it) for i, it in enumerate(items) if it is not None]
    for pos, (i, entry) in enumerate(selectable):
        label = entry[0] if isinstance(entry, tuple) else entry
        print(f"    [{pos + 1}]  {label}")
    try:
        raw = input("\n  Choice (0 = quit): ").strip()
        n   = int(raw)
        if n == 0:
            return None
        if 1 <= n <= len(selectable):
            return selectable[n - 1][0]
    except (ValueError, EOFError):
        pass
    return None


def _select(section: str, items: list) -> int | None:
    if _IS_TTY and _HAS_TERMIOS:
        return _menu_select(section, items)
    return _fallback_select(section, items)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main():
    all_configs = _discover_configs()

    while True:
        # ── Level 1: choose mode ─────────────────────────────────────────────
        mode_items = [(m["label"], "") for m in _MODES]
        mode_items.append(None)                        # visual separator
        mode_items.append(("Quit", ""))

        try:
            choice = _select("Select a run mode:", mode_items)
        except KeyboardInterrupt:
            choice = None

        if choice is None or isinstance(mode_items[choice], str) and mode_items[choice] == "Quit" \
                or mode_items[choice] == ("Quit", ""):
            if _IS_TTY:
                sys.stdout.write(_CLEAR); sys.stdout.flush()
            print("\n  Goodbye.\n")
            return

        selected_mode = _MODES[choice]

        # ── Level 2: choose config ───────────────────────────────────────────
        matching = [c for c in all_configs if c["mode"] == selected_mode["mode"]]

        if not matching:
            print(
                f"\n  No config files found for mode '{selected_mode['mode']}'.\n"
                f"  Add a config_*.py to config/ with CONFIG_TITLE and "
                f"run_mode='{selected_mode['mode']}'.\n"
            )
            input("  Press Enter to go back…")
            continue

        cfg_items = [
            (c["title"], _c(_DIM, c["filename"])) for c in matching
        ]
        cfg_items.append(None)                         # visual separator
        cfg_items.append(("← Back", ""))

        section = f"{selected_mode['label']}  →  Select a config:"

        try:
            cfg_choice = _select(section, cfg_items)
        except KeyboardInterrupt:
            cfg_choice = None

        # "← Back" is the last selectable item
        back_idx = next(i for i, it in enumerate(cfg_items) if it == ("← Back", ""))
        if cfg_choice is None or cfg_choice == back_idx:
            continue   # back to mode selection

        chosen = matching[cfg_choice]

        # ── Launch ───────────────────────────────────────────────────────────
        if _IS_TTY:
            sys.stdout.write(_CLEAR); sys.stdout.flush()

        from src.banner import print_banner, print_footer
        print_banner(chosen["title"])

        try:
            runner = importlib.import_module(selected_mode["runner"])
            runner.main(chosen["data"])
        except ValueError as e:
            # Mode mismatch or config validation error from the runner
            print(f"\n  [ERROR] {e}\n")
        except KeyboardInterrupt:
            pass
        finally:
            print_footer(chosen["title"])

        break   # exit after one run


if __name__ == "__main__":
    main()
