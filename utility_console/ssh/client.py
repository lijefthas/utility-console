"""
SSH/SCP utilities: options, password injection via SSH_ASKPASS, file extraction, cleanup.
"""

import sys
import os
import base64
import tempfile
import subprocess
import shutil
import zipfile
import gzip

SSH_OPTS          = ["-oHostKeyAlgorithms=+ssh-rsa", "-oStrictHostKeyChecking=accept-new"]
SSH_OPTS_KEEPALIVE = SSH_OPTS + ["-oServerAliveInterval=10", "-oServerAliveCountMax=6"]
DEFAULT_PASS      = "4oti0nly"
WIN_FLAGS         = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _make_askpass(password: str):
    """Write a batch+py pair that echoes the password for SSH_ASKPASS."""
    b64 = base64.b64encode(password.encode()).decode()
    with tempfile.NamedTemporaryFile(mode="w", suffix="_askpass.py", delete=False) as f:
        f.write(f"import base64,sys\nsys.stdout.write(base64.b64decode(b'{b64}').decode())\n")
        py_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix="_askpass.bat", delete=False) as f:
        f.write(f'@echo off\n"{sys.executable}" "{py_path}"\n')
        bat_path = f.name
    return bat_path, [py_path, bat_path]


def ssh_env(password: str):
    """Return an env dict and temp-file path list for SSH_ASKPASS-based auth."""
    bat, paths = _make_askpass(password)
    env = os.environ.copy()
    env["SSH_ASKPASS"]         = bat
    env["SSH_ASKPASS_REQUIRE"] = "force"
    return env, paths


def cleanup(paths: list):
    """Delete temporary files, ignoring errors."""
    for p in paths:
        try:
            os.unlink(p)
        except Exception:
            pass


def extract_gz(gz_path: str) -> str | None:
    """Try zip format first, fall back to gzip. Returns output path or None on failure."""
    out_path = os.path.splitext(gz_path)[0] + ".log"
    dest_dir = os.path.dirname(gz_path) or "."
    try:
        with zipfile.ZipFile(gz_path, 'r') as zf:
            inner = zf.namelist()[0]
            zf.extract(inner, dest_dir)
            os.rename(os.path.join(dest_dir, inner), out_path)
            return out_path
    except zipfile.BadZipFile:
        pass
    try:
        with gzip.open(gz_path, 'rb') as f_in, open(out_path, 'wb') as f_out:
            shutil.copyfileobj(f_in, f_out)
        return out_path
    except EOFError:
        return None
    except Exception:
        return None
