"""
Background QThread workers for all SSH/SCP operations.
Each worker emits signals and never touches the GUI directly.
"""

import sys
import os
import shlex
import subprocess
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from utility_console.ssh.client import SSH_OPTS, SSH_OPTS_KEEPALIVE, WIN_FLAGS, ssh_env, cleanup, extract_gz
from utility_console.os.device import parse_ls_line, CMD_SYSTEM, module_path, tgz_extract_dir, detect_modules, DIR_TMP
from utility_console.db.queries import (mysql_cmd, SQL_LIST_MODULES, SQL_SELECT_LAST_UNFINALIZED_TRANSACTION,
                     sql_set_module_status)


def _run_ssh(ip, port, username, env, cmd_str, timeout=90):
    """Run a single SSH command and return (returncode, stdout, stderr)."""
    cmd = ["ssh"] + SSH_OPTS_KEEPALIVE + [
        "-p", str(port), f"{username}@{ip}", cmd_str,
    ]
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, env=env, creationflags=WIN_FLAGS, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _run_stopall(ip, port, username, env, log_fn, timeout=120):
    """Run stopall on the VIS, stream output via log_fn. Returns (rc, stderr)."""
    rc, out, err = _run_ssh(ip, port, username, env, "bash /root/epr/stopall", timeout=timeout)
    for line in f"{out}\n{err}".splitlines():
        if line.strip():
            log_fn(line)
    return rc, err


_CONN_ERRS = (
    "Connection refused", "Connection reset", "Network error",
    "timed out", "Broken pipe", "No route to host", "Connection closed",
)


def _is_conn_err(err: str) -> bool:
    return any(s.lower() in err.lower() for s in _CONN_ERRS)


def _ssh_retry(ip, port, username, env, cmd, log_fn=None, retries=3, timeout=90):
    """_run_ssh with reconnect retry on SSH connection loss."""
    for attempt in range(retries):
        rc, out, err = _run_ssh(ip, port, username, env, cmd, timeout)
        if rc == 0 or not _is_conn_err(err):
            return rc, out, err
        if attempt < retries - 1:
            if log_fn:
                log_fn(f"Connection lost — reconnecting (attempt {attempt + 2}/{retries}) ...")
            time.sleep(5)
    return rc, out, err


def _scp_with_retry(env, ip, port, username, local_path, remote_path, log_fn, error_fn):
    """SCP local_path → remote_path with one retry on timeout. Emits via log_fn/error_fn. Returns True on success."""
    name = os.path.basename(local_path)
    scp  = ["scp"] + SSH_OPTS_KEEPALIVE + [
        "-P", str(port), local_path, f"{username}@{ip}:{remote_path}",
    ]
    def _do():
        return subprocess.run(scp, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, env=env, creationflags=WIN_FLAGS, timeout=120)
    try:
        r = _do()
    except subprocess.TimeoutExpired:
        log_fn(f"Upload timed out — retrying {name} ...")
        try:
            r = _do()
        except subprocess.TimeoutExpired:
            error_fn(f"Upload timed out twice: {name}")
            return False
    if r.returncode != 0:
        error_fn(f"Upload failed ({name}): {r.stderr.strip()}")
        return False
    return True


def _mysql_run(ssh_fn, remote_path, log_fn, error_fn, timeout=120):
    """Execute mysql < remote_path via ssh_fn, log output. Returns True on success."""
    log_fn(f"[SQL] mysql < {shlex.quote(remote_path)}")
    rc, out, err = ssh_fn(f"mysql < {shlex.quote(remote_path)}", timeout=timeout)
    for line in out.splitlines():
        if line.strip():
            log_fn(f"[SQL] {line}")
    if rc != 0:
        error_fn(f"SQL failed ({os.path.basename(remote_path)}): {err.strip() or out.strip()}")
        return False
    log_fn(f"[SQL] {os.path.basename(remote_path)} — OK")
    return True


class PingWorker(QThread):
    output   = pyqtSignal(str)
    result   = pyqtSignal(bool)
    finished = pyqtSignal()

    def __init__(self, ip: str):
        super().__init__()
        self.ip = ip

    def run(self):
        cmd = (["ping", "-n", "4", self.ip] if sys.platform == "win32"
               else ["ping", "-c", "4", self.ip])
        ok = False
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, creationflags=WIN_FLAGS)
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    self.output.emit(line)
            proc.wait()
            ok = proc.returncode == 0
        except Exception as e:
            self.output.emit(f"Ping error: {e}")
        self.result.emit(ok)
        self.finished.emit()


class ListWorker(QThread):
    """Lists files from one or more remote directories.
    Emits (date, filename, size, full_path) tuples."""
    files_ready = pyqtSignal(list)
    log         = pyqtSignal(str)
    error       = pyqtSignal(str)

    def __init__(self, ip, port, username, password, remote_dirs):
        super().__init__()
        self.ip, self.port, self.username = ip, port, username
        self.password    = password
        self.remote_dirs = remote_dirs  # [(dir, pattern), ...]

    def run(self):
        dirs_str = ", ".join(d for d, _ in self.remote_dirs)
        self.log.emit(f"Listing {dirs_str} ...")
        env, paths = ssh_env(self.password)
        globs = " ".join(f"{d}/{p}" for d, p in self.remote_dirs)
        cmd = ["ssh"] + SSH_OPTS + [
            "-p", str(self.port), f"{self.username}@{self.ip}",
            f"ls -laht {globs} 2>/dev/null || true",
        ]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env, creationflags=WIN_FLAGS, timeout=30)
            if r.returncode != 0 and not r.stdout.strip():
                self.error.emit(r.stderr.strip() or "Connection failed.")
                return
            lines  = [s for l in r.stdout.splitlines()
                      if (s := l.strip()) and not s.startswith("total")]
            parsed = [p for p in (parse_ls_line(l) for l in lines) if p]
            self.log.emit(f"Found {len(parsed)} file(s).")
            self.files_ready.emit(parsed)
        except subprocess.TimeoutExpired:
            self.error.emit("SSH listing timed out after 30 s")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class DownloadWorker(QThread):
    """Downloads files by their full remote paths via SCP."""
    progress = pyqtSignal(int, int)
    log      = pyqtSignal(str)
    warn     = pyqtSignal(str)
    error    = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, ip, port, username, password, remote_paths, local_dir):
        super().__init__()
        self.ip, self.port, self.username = ip, port, username
        self.password     = password
        self.remote_paths = remote_paths  # list of full remote paths
        self.local_dir    = local_dir

    def run(self):
        env, paths = ssh_env(self.password)
        total = len(self.remote_paths)
        try:
            for i, remote_path in enumerate(self.remote_paths):
                filename = os.path.basename(remote_path)
                self.progress.emit(i, total)
                self.log.emit(f"Downloading {filename} ({i + 1}/{total}) ...")
                remote = f"{self.username}@{self.ip}:{remote_path}"
                local  = os.path.join(self.local_dir, filename)
                cmd    = ["scp"] + SSH_OPTS + ["-P", str(self.port), remote, local]
                try:
                    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       env=env, creationflags=WIN_FLAGS)
                    if r.returncode == 0:
                        self.log.emit(f"Saved: {local}")
                        if filename.endswith('.gz'):
                            out = extract_gz(local)
                            if out:
                                self.log.emit(f"Extracted: {os.path.basename(out)}")
                                os.unlink(local)
                            else:
                                self.warn.emit(f"Extraction failed — keeping original: {local}")
                    else:
                        self.error.emit(f"Failed {filename}: {r.stderr.decode().strip()}")
                except Exception as e:
                    self.error.emit(str(e))
        finally:
            cleanup(paths)
        self.progress.emit(total, total)
        self.finished.emit()


class ConnectWorker(QThread):
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password

    def run(self):
        env, paths = ssh_env(self.password)
        cmd = ["ssh"] + SSH_OPTS + [
            "-p", str(self.port), f"{self.username}@{self.ip}", "exit",
        ]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, env=env, creationflags=WIN_FLAGS, timeout=10)
            if r.returncode == 0:
                self.success.emit()
            else:
                self.error.emit(r.stderr.strip() or "Connection failed")
        except subprocess.TimeoutExpired:
            self.error.emit("Connection timed out")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class ScriptWorker(QThread):
    """Runs an arbitrary shell command on the VIS over SSH, streaming output."""
    log     = pyqtSignal(str)
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password, command, timeout=None):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.command    = command
        self._timeout   = timeout
        self._proc      = None
        self._timed_out = False

    def run(self):
        env, paths = ssh_env(self.password)
        cmd = ["ssh"] + SSH_OPTS + [
            "-p", str(self.port), f"{self.username}@{self.ip}",
            self.command,
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, creationflags=WIN_FLAGS,
            )
            _timer = None
            if self._timeout:
                def _on_timeout():
                    self._timed_out = True
                    if self._proc.poll() is None:
                        self._proc.kill()
                _timer = threading.Timer(self._timeout, _on_timeout)
                _timer.start()
            for line in self._proc.stdout:
                line = line.rstrip()
                if line:
                    self.log.emit(line)
            if _timer:
                _timer.cancel()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            if self._proc.returncode == 0 or self._timed_out:
                self.success.emit()
            else:
                self.error.emit(f"Exited with code {self._proc.returncode}")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if self._proc is not None:
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
            cleanup(paths)

    def stop(self):
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass


class SystemWorker(QThread):
    """Queries all epr_modules and their running state on the VIS."""
    result = pyqtSignal(list)   # list of {"pid": str|None, "name": str, "running": bool}
    error  = pyqtSignal(str)

    def __init__(self, ip, port, username, password):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password

    def run(self):
        env, paths = ssh_env(self.password)
        try:
            # All modules from DB (authoritative list)
            rc, out, _ = _run_ssh(
                self.ip, self.port, self.username, env,
                mysql_cmd(SQL_LIST_MODULES, "eprvi"),
                timeout=15,
            )
            all_names = [l.strip() for l in out.splitlines() if l.strip()] if rc == 0 else []

            # Currently running epr processes with PIDs
            _, ps_out, _ = _run_ssh(self.ip, self.port, self.username, env, CMD_SYSTEM, timeout=15)
            running = {}
            for line in ps_out.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    running[parts[1]] = parts[0]  # name → pid

            # Merge: DB list first, then any extra running processes not in DB
            seen  = set()
            items = []
            for name in all_names:
                pid = running.get(name)
                items.append({"pid": pid, "name": name, "running": pid is not None})
                seen.add(name)
            for name, pid in running.items():
                if name not in seen:
                    items.append({"pid": pid, "name": name, "running": True})

            self.result.emit(items)
        except subprocess.TimeoutExpired:
            self.error.emit("System check timed out")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class ModuleControlWorker(QThread):
    """Updates epr_modules status in MySQL, optionally sends SIGKILL to the process."""
    log     = pyqtSignal(str)
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password, name, pid=None):
        # pid=None  → start action (status='1', no kill)
        # pid set   → kill action  (status='0', then kill -9)
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.name = name
        self.pid  = pid

    def run(self):
        action = "kill" if self.pid else "start"
        status = "0"    if self.pid else "1"
        env, paths = ssh_env(self.password)
        try:
            self.log.emit(f"[{action}] Setting {self.name} status → {status} ...")
            rc, out, err = _run_ssh(
                self.ip, self.port, self.username, env,
                mysql_cmd(sql_set_module_status(self.name, status), "eprvi"),
            )
            if rc != 0:
                self.error.emit(f"MySQL update failed: {err or out}")
                return
            self.log.emit(f"[{action}] DB updated.")
            if self.pid:
                self.log.emit(f"[kill] SIGKILL → PID {self.pid} ({self.name}) ...")
                rc, out, err = _run_ssh(
                    self.ip, self.port, self.username, env, f"kill -9 {self.pid}")
                if rc != 0:
                    self.error.emit(f"kill -9 failed: {err or out}")
                    return
                self.log.emit(f"[kill] PID {self.pid} killed.")
            self.success.emit()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class SqlQueryWorker(QThread):
    """Runs a MySQL query on the VIS and emits the result rows."""
    result = pyqtSignal(list)
    error  = pyqtSignal(str)

    def __init__(self, ip, port, username, password, query, database=None, with_headers=False):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.query        = query
        self.database     = database
        self.with_headers = with_headers

    def run(self):
        env, paths = ssh_env(self.password)
        try:
            rc, out, err = _run_ssh(
                self.ip, self.port, self.username, env,
                mysql_cmd(self.query, self.database, self.with_headers),
                timeout=15,
            )
            if rc != 0:
                self.error.emit(err or out or "Query failed")
                return
            rows = [l.strip() for l in out.splitlines() if l.strip()]
            self.result.emit(rows)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class TailWorker(QThread):
    """Streams tail -f output from a remote file over SSH."""
    line = pyqtSignal(str)

    def __init__(self, ip, port, username, password, remote_path):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.remote_path = remote_path
        self._proc = None

    def run(self):
        env, paths = ssh_env(self.password)
        cmd = ["ssh"] + SSH_OPTS + [
            "-p", str(self.port), f"{self.username}@{self.ip}",
            f"tail -f {self.remote_path}",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, creationflags=WIN_FLAGS,
            )
            for line in self._proc.stdout:
                self.line.emit(line.rstrip("\n"))
        except Exception as e:
            self.line.emit(f"[error] {e}")
        finally:
            if self._proc is not None:
                try:
                    self._proc.stdout.close()
                except Exception:
                    pass
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
            cleanup(paths)

    def stop(self):
        proc = self._proc
        if proc is not None:
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.stdout.close()
            except Exception:
                pass


# ── Module update workers ─────────────────────────────────────────────────────

_TXN_DISPLAY_FIELDS = (
    "token", "date_time", "controller_reference",
    "pump", "nozzle", "sale_volume", "sale_value",
)


class TransactionCheckWorker(QThread):
    """Checks for an ongoing (unfinalized) transaction on the VIS.
    Emits clear() if none found, blocked(dict) if one exists."""
    clear   = pyqtSignal()
    blocked = pyqtSignal(dict)
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password

    def run(self):
        env, paths = ssh_env(self.password)
        try:
            cmd = mysql_cmd(SQL_SELECT_LAST_UNFINALIZED_TRANSACTION, "eprvi", with_headers=True)
            rc, out, err = _run_ssh(self.ip, self.port, self.username, env, cmd, timeout=15)
            if rc != 0:
                self.error.emit(err or "Transaction check failed")
                return
            lines = [l for l in out.splitlines() if l.strip()]
            if len(lines) < 2:
                self.clear.emit()
                return
            headers = lines[0].split("\t")
            values  = lines[1].split("\t")
            self.blocked.emit(dict(zip(headers, values)))
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class UpdateWorker(QThread):
    """Stops all, backs up, uploads, and chmods a single EPR module."""
    log     = pyqtSignal(str)
    step    = pyqtSignal(str)   # short progress description for the status bar
    success = pyqtSignal(str)   # module name on success
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password, local_file, module_name):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.local_file  = local_file
        self.module_name = module_name

    def _upload(self, env, mdir):
        """SCP the local file to <mdir>/<module>. Returns True on success."""
        remote  = f"{self.username}@{self.ip}:{mdir}/{self.module_name}"
        scp_cmd = ["scp"] + SSH_OPTS_KEEPALIVE + [
            "-P", str(self.port), self.local_file, remote,
        ]
        r = subprocess.run(scp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, env=env, creationflags=WIN_FLAGS, timeout=120)
        if r.returncode != 0:
            self.error.emit(f"Upload failed: {r.stderr.strip()}")
            return False
        self.log.emit(f"Uploaded {self.module_name} to {mdir}/")
        return True

    def _deploy(self, env, mdir):
        """Upload + chmod with one upload retry on timeout. Returns True on success."""
        m = self.module_name
        self.step.emit(f"Uploading {m} ...")
        try:
            if not self._upload(env, mdir):
                return False
        except subprocess.TimeoutExpired:
            self.step.emit(f"Re-uploading {m} after timeout ...")
            self.log.emit("Upload timed out — retrying ...")
            if not self._upload(env, mdir):
                return False
        self.step.emit("Setting permissions ...")
        rc, _, err = _run_ssh(self.ip, self.port, self.username, env,
                              f"chmod 755 {mdir}/{m}", timeout=30)
        if rc != 0:
            self.error.emit(f"chmod failed: {err}")
            return False
        self.log.emit(f"chmod 755 {mdir}/{m} — OK")
        return True

    def run(self):
        env, paths = ssh_env(self.password)
        m    = self.module_name
        mdir = module_path(m)
        try:
            self.step.emit(f"Verifying {m} on server ...")
            rc, out, _ = _run_ssh(self.ip, self.port, self.username, env,
                                  f"test -f {mdir}/{m} && echo found || echo missing",
                                  timeout=15)
            if rc != 0 or "missing" in out:
                self.error.emit(f"{m} not found at {mdir}/{m} on the server")
                return
            self.log.emit(f"Found {mdir}/{m} on server.")

            self.step.emit("Stopping all modules ...")
            rc, err = _run_stopall(self.ip, self.port, self.username, env, self.log.emit)
            if rc != 0:
                self.error.emit(f"stopall failed (rc={rc}): {err}")
                return

            self.step.emit("Backing up existing module ...")
            bak_cmd = (
                f"DATE=$(date +%d%m%Y);"
                f" mkdir -p /var/bak/epr;"
                f" cp {mdir}/{m} /var/bak/epr/{m}_$DATE &&"
                f" echo /var/bak/epr/{m}_$DATE"
            )
            rc, bak_out, err = _run_ssh(self.ip, self.port, self.username, env, bak_cmd)
            if rc != 0:
                self.error.emit(f"Backup failed: {err}")
                return
            self.log.emit(f"Backed up to {bak_out}")

            if not self._deploy(env, mdir):
                return
            self.success.emit(m)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class RollbackWorker(QThread):
    """Stops all then restores the most recent backup from /var/bak/epr/."""
    log     = pyqtSignal(str)
    step    = pyqtSignal(str)
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password, module_name):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.module_name = module_name

    def run(self):
        env, paths = ssh_env(self.password)
        m    = self.module_name
        mdir = module_path(m)
        try:
            self.step.emit("Finding latest backup ...")
            rc, latest, _ = _run_ssh(self.ip, self.port, self.username, env,
                                     f"ls -t /var/bak/epr/{m}_* 2>/dev/null | head -1",
                                     timeout=15)
            if not latest:
                self.error.emit(f"No backup found for {m} in /var/bak/epr/")
                return
            self.log.emit(f"Found backup: {latest}")

            self.step.emit("Stopping all modules ...")
            rc, err = _run_stopall(self.ip, self.port, self.username, env, self.log.emit)
            if rc != 0:
                self.error.emit(f"stopall failed: {err}")
                return

            self.step.emit("Restoring backup ...")
            rc, _, err = _run_ssh(self.ip, self.port, self.username, env,
                                  f"cp {latest} {mdir}/{m} && chmod 755 {mdir}/{m}")
            if rc != 0:
                self.error.emit(f"Restore failed: {err}")
                return
            self.log.emit(f"Restored {mdir}/{m} from {latest}")
            self.success.emit()

        except subprocess.TimeoutExpired:
            self.error.emit("Operation timed out")
        except Exception as e:
            self.error.emit(str(e))
        finally:
            cleanup(paths)


class TgzUpdateWorker(QThread):
    """Uploads a .tgz package to /tmp, extracts it, updates EPR modules, runs SQL."""
    log     = pyqtSignal(str)
    step    = pyqtSignal(str)
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password, local_file):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.local_file = local_file

    def _ssh(self, env, cmd, timeout=90):
        return _ssh_retry(self.ip, self.port, self.username, env, cmd,
                          log_fn=self.log.emit, timeout=timeout)

    def _upload_tgz(self, env, remote_path):
        """SCP local .tgz to remote_path with one retry on timeout. Returns True on success."""
        ok = _scp_with_retry(env, self.ip, self.port, self.username, self.local_file,
                             remote_path, self.log.emit, self.error.emit)
        if ok:
            self.log.emit(f"Uploaded package to {remote_path}")
        return ok

    def _extract(self, env, tgz_path, extract_dir):
        """Create extract dir and untar. Returns True on success."""
        rc, _, err = self._ssh(env,
                               f"mkdir -p '{extract_dir}' && tar -xf '{tgz_path}' -C '{extract_dir}'",
                               timeout=120)
        if rc != 0:
            self.error.emit(f"Extraction failed: {err}")
            return False
        self.log.emit(f"Extracted to {extract_dir}")
        return True

    def _list_dir(self, env, extract_dir):
        """Return list of filenames in extract_dir (top-level). Returns None on error."""
        rc, out, err = self._ssh(env, f"ls -1 '{extract_dir}' 2>/dev/null", timeout=15)
        if rc != 0:
            self.error.emit(f"Cannot list {extract_dir}: {err}")
            return None
        return [f.strip() for f in out.splitlines() if f.strip()]

    def _backup_module(self, env, m, mdir):
        """Backup existing module if present. Returns True on success."""
        _, out, _ = self._ssh(env, f"test -f '{mdir}/{m}' && echo found || echo missing", timeout=15)
        if out.strip() == "missing":
            self.log.emit(f"{m} not found on server — skipping backup (new module)")
            return True
        bak = (f"DATE=$(date +%d%m%Y); mkdir -p /var/bak/epr;"
               f" cp '{mdir}/{m}' /var/bak/epr/{m}_$DATE && echo /var/bak/epr/{m}_$DATE")
        rc, bak_out, err = self._ssh(env, bak)
        if rc != 0:
            self.error.emit(f"Backup failed for {m}: {err}")
            return False
        self.log.emit(f"Backed up {m} → {bak_out}")
        return True

    def _deploy_module(self, env, m, mdir, src_path):
        """Copy module from src_path to dest and chmod 755. Returns True on success."""
        rc, _, err = self._ssh(env,
                               f"cp '{src_path}' '{mdir}/{m}' && chmod 755 '{mdir}/{m}'",
                               timeout=60)
        if rc != 0:
            self.error.emit(f"Deploy failed for {m}: {err}")
            return False
        self.log.emit(f"Deployed {m} → {mdir}/{m}")
        return True

    def _update_modules(self, env, extract_dir, modules):
        """stopall once then backup + deploy each module. Returns True on success."""
        self.step.emit("Stopping all modules ...")
        rc, err = _run_stopall(self.ip, self.port, self.username, env, self.log.emit)
        if rc != 0:
            self.error.emit(f"stopall failed (rc={rc}): {err}")
            return False
        for m in modules:
            mdir = module_path(m)
            self.step.emit(f"Backing up {m} ...")
            if not self._backup_module(env, m, mdir):
                return False
            self.step.emit(f"Deploying {m} ...")
            if not self._deploy_module(env, m, mdir, f"{extract_dir}/{m}"):  # m has no spaces (KNOWN_MODULES)
                return False
        return True

    def _run_sql_files(self, env, extract_dir, sql_files):
        """Run each .sql file via mysql and log output. Returns True on success."""
        ssh_fn = lambda cmd, timeout=90: self._ssh(env, cmd, timeout)
        for sql in sql_files:
            self.step.emit(f"Running {sql} ...")
            if not _mysql_run(ssh_fn, f"{extract_dir}/{sql}", self.log.emit, self.error.emit):
                return False
        return True

    def _cleanup(self, env, tgz_path, extract_dir):
        self._ssh(env, f"rm -f '{tgz_path}' && rm -rf '{extract_dir}'", timeout=30)
        self.log.emit(f"Cleaned up {tgz_path} and {extract_dir}")

    def _scan(self, env, extract_dir):
        """List dir, detect modules and SQL files. Returns (modules, sql_files) or (None, None)."""
        filenames = self._list_dir(env, extract_dir)
        if filenames is None:
            return None, None
        modules   = detect_modules(filenames)
        sql_files = [f for f in filenames if f.endswith(".sql")]
        self.log.emit(f"Package: {len(modules)} module(s), {len(sql_files)} SQL file(s)")
        return modules, sql_files

    def run(self):
        env, paths  = ssh_env(self.password)
        tgz_name    = os.path.basename(self.local_file)
        remote_tgz  = f"{DIR_TMP}/{tgz_name}"
        extract_dir = tgz_extract_dir(tgz_name)
        uploaded = False
        ok       = False
        try:
            self.step.emit("Uploading package ...")
            if not self._upload_tgz(env, remote_tgz):
                return
            uploaded = True
            self.step.emit("Extracting package ...")
            if not self._extract(env, remote_tgz, extract_dir):
                return
            self.step.emit("Scanning contents ...")
            modules, sql_files = self._scan(env, extract_dir)
            if modules is None:
                return
            if not modules and not sql_files:
                self.error.emit("Package contains no recognised modules or SQL files")
                return
            if modules:
                self.step.emit("Updating modules ...")
                if not self._update_modules(env, extract_dir, modules):
                    return
            if sql_files:
                self.step.emit("Running SQL migrations ...")
                if not self._run_sql_files(env, extract_dir, sql_files):
                    return
            ok = True
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if uploaded:
                self.step.emit("Cleaning up ...")
                self._cleanup(env, remote_tgz, extract_dir)
            cleanup(paths)
        if ok:
            self.success.emit()


class SqlFileWorker(QThread):
    """Uploads one or more .sql files to /tmp and runs each via mysql."""
    log     = pyqtSignal(str)
    step    = pyqtSignal(str)
    success = pyqtSignal()
    error   = pyqtSignal(str)

    def __init__(self, ip, port, username, password, local_files: list):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.local_files = local_files

    def _ssh(self, env, cmd, timeout=90):
        return _ssh_retry(self.ip, self.port, self.username, env, cmd,
                          log_fn=self.log.emit, timeout=timeout)

    def _upload(self, env, local_path):
        """SCP local_path to /tmp/<basename>. Returns remote path or None on failure."""
        name   = os.path.basename(local_path)
        remote = f"{DIR_TMP}/{name}"
        ok = _scp_with_retry(env, self.ip, self.port, self.username, local_path,
                             remote, self.log.emit, self.error.emit)
        if ok:
            self.log.emit(f"Uploaded {name} → {remote}")
        return remote if ok else None

    def _run_sql(self, env, remote_path):
        return _mysql_run(
            lambda cmd, timeout=90: self._ssh(env, cmd, timeout),
            remote_path, self.log.emit, self.error.emit,
        )

    def _cleanup(self, env, uploaded: list):
        quoted = " ".join(shlex.quote(p) for p in uploaded)
        self._ssh(env, f"rm -f {quoted}", timeout=30)
        self.log.emit(f"Cleaned up {len(uploaded)} file(s) from /tmp/")

    def run(self):
        env, paths = ssh_env(self.password)
        n        = len(self.local_files)
        uploaded = []
        ok       = False
        try:
            for i, local in enumerate(self.local_files, 1):
                self.step.emit(f"Uploading {os.path.basename(local)} ({i}/{n}) ...")
                remote = self._upload(env, local)
                if remote is None:
                    return
                uploaded.append(remote)
            for remote in uploaded:
                self.step.emit(f"Running {os.path.basename(remote)} ...")
                if not self._run_sql(env, remote):
                    return
            ok = True
        except Exception as e:
            self.error.emit(str(e))
        finally:
            if uploaded:
                self.step.emit("Cleaning up ...")
                self._cleanup(env, uploaded)
            cleanup(paths)
        if ok:
            self.success.emit()


class TestModuleWorker(QThread):
    """Runs /root/epr/<module> over SSH and streams output.
    Emits running() if still alive 3 s after start."""
    line    = pyqtSignal(str)
    running = pyqtSignal()    # still alive after 3 s
    stopped = pyqtSignal(int) # returncode when process exits

    def __init__(self, ip, port, username, password, module_name):
        super().__init__()
        self.ip, self.port           = ip, port
        self.username, self.password = username, password
        self.module_name = module_name
        self._proc = None

    def run(self):
        env, paths = ssh_env(self.password)
        cmd = ["ssh"] + SSH_OPTS_KEEPALIVE + [
            "-p", str(self.port), f"{self.username}@{self.ip}",
            f"{module_path(self.module_name)}/{self.module_name}",
        ]
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, env=env, creationflags=WIN_FLAGS,
            )

            def _heartbeat():
                time.sleep(3)
                if self._proc and self._proc.poll() is None:
                    self.running.emit()

            threading.Thread(target=_heartbeat, daemon=True).start()

            for line in self._proc.stdout:
                self.line.emit(line.rstrip("\n"))
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
            self.stopped.emit(self._proc.returncode)
        except Exception as e:
            self.line.emit(f"[error] {e}")
            self.stopped.emit(-1)
        finally:
            if self._proc is not None:
                try:
                    self._proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._proc.kill()
                    self._proc.wait()
            cleanup(paths)

    def stop(self):
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass


# ── GitLab / Developer workers ────────────────────────────────────────────────

class GitLabProjectsWorker(QThread):
    result = pyqtSignal(list)
    error  = pyqtSignal(str)

    def __init__(self, gitlab_url: str, token: str):
        super().__init__()
        self._url   = gitlab_url.rstrip("/")
        self._token = token

    def run(self):
        import urllib.request
        import urllib.error
        import json as _json

        try:
            req = urllib.request.Request(
                f"{self._url}/api/v4/projects?membership=true&per_page=100&order_by=last_activity_at",
                headers={"PRIVATE-TOKEN": self._token},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = _json.loads(resp.read().decode())
            projects = [
                {
                    "name_with_namespace": p.get("name_with_namespace", ""),
                    "description": p.get("description") or "",
                }
                for p in data
            ]
            self.result.emit(projects)
        except urllib.error.HTTPError as e:
            self.error.emit(f"HTTP {e.code}: {e.reason}")
        except Exception as e:
            self.error.emit(str(e))


class CopyBinaryWorker(QThread):
    log     = pyqtSignal(str)
    success = pyqtSignal(str)
    error   = pyqtSignal(str)

    def __init__(self, wsl_user: str, src_wsl_path: str, dst_dir_wsl: str, distro: str = "Ubuntu"):
        super().__init__()
        self._user    = wsl_user
        self._src     = src_wsl_path
        self._dst_dir = dst_dir_wsl
        self._distro  = distro

    def run(self):
        name     = os.path.basename(self._src)
        bash_cmd = f"mkdir -p {self._dst_dir} && cp {self._src} {self._dst_dir}/{name}"
        try:
            self.log.emit(f"wsl -u {self._user}: {bash_cmd}")
            r = subprocess.run(
                ["wsl.exe", "-u", self._user, "--", "bash", "-c", bash_cmd],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, creationflags=WIN_FLAGS, timeout=30,
            )
            if r.returncode != 0:
                self.error.emit(r.stderr.strip() or "Copy failed (no error message)")
                return
            dst_linux = f"{self._dst_dir}/{name}"
            unc_path  = "\\\\wsl$\\" + self._distro + dst_linux.replace("/", "\\")
            self.log.emit(f"Binary available at: {unc_path}")
            self.success.emit(unc_path)
        except subprocess.TimeoutExpired:
            self.error.emit("Timed out (30 s) waiting for WSL copy")
        except Exception as e:
            self.error.emit(str(e))
