"""
VIS device constants: remote directories, shell commands, and ls output parsing.
"""

import os
from datetime import datetime

DIR_LIVE = "/root/epr"
DIR_ARCH = "/root/epr/logs"
DIR_ROOT = "/root"
DIR_TMP  = "/tmp"

LIVE_LOG_DIRS = [(DIR_LIVE, "*.log"), (DIR_ROOT, "*.log")]
ARCH_LOG_DIRS = [(DIR_ARCH, "*")]

CMD_ROTATE   = "cd /root/epr && bash rotatescript.sh -f"
CMD_STOPALL  = "bash /root/epr/stopall"
CMD_STARTALL = (
    "echo '[startall] connected';"
    " setsid bash /root/epr/startall < /dev/null > /dev/null 2>&1 &"
    " echo '[startall] launched (PID '$!')'; echo '[startall] done'"
)
CMD_SYSTEM   = "ps -eo pid,comm | grep epr 2>/dev/null || true"

KNOWN_MODULES = frozenset({
    "eprvi", "eprtip", "eprtap", "eprscm",
    "eprwatchdog", "eprwatchdog_ter", "eprcron",
    "eprftp", "eprstate", "eprmedia5", "epreps",
})

ROOT_MODULES = frozenset({"eprmedia5"})


def module_path(name: str) -> str:
    """Return the remote directory for a given module (DIR_ROOT or DIR_LIVE)."""
    return DIR_ROOT if name in ROOT_MODULES else DIR_LIVE


def tgz_extract_dir(tgz_name: str) -> str:
    """Return the remote extract dir for a .tgz file: /tmp/<stem>"""
    stem = tgz_name[:-4] if tgz_name.endswith(".tgz") else tgz_name
    return f"{DIR_TMP}/{stem}"


def detect_modules(filenames: list) -> list:
    """Return filenames that are in KNOWN_MODULES, preserving order."""
    return [f for f in filenames if f in KNOWN_MODULES]


def parse_ls_line(line: str):
    """Parse one ls -laht line → (date, filename, size, full_path) or None."""
    parts = line.split()
    if len(parts) < 9 or not parts[0].startswith("-"):
        return None
    size      = parts[4]
    date      = f"{parts[5]} {int(parts[6]):>2} {parts[7]}"
    full_path = parts[-1]
    filename  = os.path.basename(full_path)
    return date, filename, size, full_path


def parse_size(s: str) -> float:
    """Convert human-readable size (e.g. '2.3M', '512K') to bytes for sorting."""
    s = s.strip()
    units = {'K': 1e3, 'M': 1e6, 'G': 1e9, 'T': 1e12}
    if s and s[-1].upper() in units:
        try:
            return float(s[:-1]) * units[s[-1].upper()]
        except ValueError:
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_date_key(date_str: str) -> float:
    """Convert ls date string ('May  5 02:00' or 'May  5 2025') to timestamp for sorting."""
    parts = date_str.split()
    if len(parts) < 3:
        return 0.0
    month, day, third = parts[0], parts[1].strip(), parts[2]
    try:
        if ':' in third:
            dt = datetime.strptime(f"{month} {day} {datetime.now().year} {third}", "%b %d %Y %H:%M")
        else:
            dt = datetime.strptime(f"{month} {day} {third}", "%b %d %Y")
        return dt.timestamp()
    except ValueError:
        return 0.0
