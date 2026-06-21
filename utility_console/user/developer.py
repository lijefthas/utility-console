"""
Developer settings - GitLab credentials, WSL config, local git directory.
Persisted in developer_settings.json alongside the app.
"""

import json
import os

_APP_DIR          = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_SETTINGS_FILE    = os.path.join(_APP_DIR, "developer_settings.json")
_BUILD_SCRIPTS_DIR = os.path.join(_APP_DIR, "build_scripts")

DEFAULTS: dict = {
    "gitlab_url":    "https://gitlab.com",
    "gitlab_email":  "",
    "gitlab_token":  "",
    "local_git_dir": "",
    "build_subpath": "{NAME}/build",
    "wsl_user":      "",
    "wsl_distro":    "Ubuntu",
    "wsl_binaries":  "/home/{USER}/binaries",
    "wsl_container": "mam",
}


def load_dev_settings() -> dict:
    try:
        with open(_SETTINGS_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        saved = {}
    return {**DEFAULTS, **saved}


def save_dev_settings(d: dict) -> None:
    tmp = _SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)
    os.replace(tmp, _SETTINGS_FILE)


def windows_to_wsl_path(path: str) -> str:
    """Convert a Windows path to the equivalent WSL /mnt/... path."""
    p = path.replace("\\", "/")
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        p = f"/mnt/{drive}{p[2:]}"
    return p


def resolve_binaries_path(settings: dict) -> str:
    """Return the WSL binaries dir with {USER} substituted."""
    return settings.get("wsl_binaries", DEFAULTS["wsl_binaries"]).replace(
        "{USER}", settings.get("wsl_user", "")
    )


def resolve_build_subpath(settings: dict, project: str) -> str:
    """Return build subpath with {NAME} replaced by project.upper()."""
    return settings.get("build_subpath", DEFAULTS["build_subpath"]).replace(
        "{NAME}", project.upper()
    )


def get_project_build_subpath(settings: dict, project: str) -> str:
    """
    Return the build subpath for a specific project.
    Checks per-project overrides first; falls back to the global template.
    Returned value is always a literal path (no {NAME} tokens).
    """
    override = settings.get("projects", {}).get(project, {}).get("build_subpath")
    if override is not None:
        return override
    return resolve_build_subpath(settings, project)


def save_project_build_subpath(project: str, subpath: str) -> None:
    """Persist a per-project build_subpath override in developer_settings.json."""
    s = load_dev_settings()
    s.setdefault("projects", {}).setdefault(project, {})["build_subpath"] = subpath
    save_dev_settings(s)


def get_project_setting(settings: dict, project: str, key: str, default=None):
    """Return a per-project setting value, or default if not set."""
    return settings.get("projects", {}).get(project, {}).get(key, default)


def save_project_setting(project: str, key: str, value: str) -> None:
    """Persist a single per-project setting in developer_settings.json."""
    s = load_dev_settings()
    s.setdefault("projects", {}).setdefault(project, {})[key] = value
    save_dev_settings(s)


def any_path_to_wsl(path: str) -> str:
    """Convert a Windows path or \\\\wsl$\\... UNC path to a WSL /... path."""
    p = path.replace("\\", "/")
    for prefix in ("//wsl$/", "//wsl.localhost/"):
        if p.lower().startswith(prefix):
            remainder = p[len(prefix):]
            slash = remainder.find("/")
            return remainder[slash:] if slash >= 0 else "/"
    if len(p) >= 2 and p[1] == ":":
        return f"/mnt/{p[0].lower()}{p[2:]}"
    return path


def get_launch_script_path(project: str) -> str:
    """Return the Windows path for the per-project docker launch script."""
    return os.path.join(_BUILD_SCRIPTS_DIR, f"{project}_launch.sh")


_STALE_FALLBACK = 'docker exec -it "$CONTAINER" bash || exec bash\n'
_NEW_FALLBACK   = 'docker exec -it "$CONTAINER" bash || mam\n'


def ensure_launch_script(project: str, container: str) -> tuple[str, bool]:
    """
    Return (windows_path, created) for the docker launch script.
    Creates the script if it does not exist.  If it already exists but still
    carries the old 'exec bash' fallback, that line is silently patched to
    use 'mam' instead (safe because 'exec bash' was only ever in the default
    template — a manually edited script would have a different last line).
    The script is a plain bash file — edit it to customise container entry.
    """
    os.makedirs(_BUILD_SCRIPTS_DIR, exist_ok=True)
    path = get_launch_script_path(project)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        if content.endswith(_STALE_FALLBACK):
            patched = content[: -len(_STALE_FALLBACK)] + _NEW_FALLBACK
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(patched)
        return path, False
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"#!/bin/bash\n")
        f.write(f"# Docker build launch script for {project}\n")
        f.write(f"# Edit this file to change how the build container is entered.\n")
        f.write(f"# Utility Console passes the container name as $1.\n")
        f.write(f"\n")
        f.write(f'CONTAINER="${{1:-{container}}}"\n')
        f.write(f'docker exec -it "$CONTAINER" bash || mam\n')
    return path, True
