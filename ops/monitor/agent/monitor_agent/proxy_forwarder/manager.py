"""
SSH 本地端口转发管理器

用于在 Linux Agent 上维护一条到 Windows 中心节点的 SSH 隧道：
    ssh -N -L 127.0.0.1:<listen>:127.0.0.1:<center_proxy_port> user@host ...
"""

import asyncio
import logging
import shutil
import socket
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

from monitor_agent.config import ProxyConfig

logger = logging.getLogger(__name__)


@dataclass
class ProxyForwarderStatus:
    status: str = "disabled"  # disabled|stopped|connecting|connected|error
    pid: Optional[int] = None
    listen_port: Optional[int] = None
    target: Optional[str] = None
    last_error: Optional[str] = None
    connected_since: Optional[str] = None
    retry_count: int = 0


def _utc_now_iso() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_port_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


class ProxyForwarderManager:
    def __init__(self):
        self._lock = asyncio.Lock()
        self._desired_running = False
        self._config: Optional[ProxyConfig] = None
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None
        self._monitor_task: Optional[asyncio.Task] = None
        self._status = ProxyForwarderStatus()

    async def configure(self, config: Optional[ProxyConfig]):
        async with self._lock:
            self._config = config
            if not config or not config.enabled:
                if not self._desired_running:
                    self._status.status = "disabled"

    async def get_status(self) -> ProxyForwarderStatus:
        async with self._lock:
            status = ProxyForwarderStatus(**self._status.__dict__)
            if self._config:
                status.listen_port = self._config.server_listen_port
                status.target = f"127.0.0.1:{self._config.center_proxy_port}"
            return status

    async def start(self, config_override: Optional[ProxyConfig] = None):
        async with self._lock:
            if config_override is not None:
                self._config = config_override

            if not self._config:
                raise ValueError("proxy config missing")
            if not self._config.enabled:
                raise ValueError("proxy is disabled in config")

            self._desired_running = True
            self._status.status = "connecting"
            self._status.last_error = None
            self._status.listen_port = self._config.server_listen_port
            self._status.target = f"127.0.0.1:{self._config.center_proxy_port}"

            # restart if already running
            if self._proc and self._proc.returncode is None:
                await self._stop_process_locked()

            if not self._monitor_task or self._monitor_task.done():
                self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self):
        async with self._lock:
            self._desired_running = False
            await self._stop_process_locked()
            self._status.status = "stopped" if (self._config and self._config.enabled) else "disabled"
            self._status.connected_since = None

            if self._monitor_task and not self._monitor_task.done():
                self._monitor_task.cancel()
            self._monitor_task = None

    async def _stop_process_locked(self):
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
        self._stderr_task = None

        proc = self._proc
        self._proc = None
        self._status.pid = None

        if not proc or proc.returncode is not None:
            return

        try:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            try:
                proc.kill()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except Exception:
                pass
        except Exception:
            pass

    def _build_ssh_command(self, cfg: ProxyConfig) -> List[str]:
        ssh_path = shutil.which("ssh")
        if not ssh_path:
            raise FileNotFoundError("ssh binary not found (openssh-client required)")

        base = [
            ssh_path,
            "-N",
            "-L",
            f"127.0.0.1:{cfg.server_listen_port}:127.0.0.1:{cfg.center_proxy_port}",
            f"{cfg.center_ssh_user}@{cfg.center_ssh_host}",
            "-p",
            str(cfg.center_ssh_port),
            "-i",
            cfg.identity_file,
            "-o",
            "BatchMode=yes",
            "-o",
            "ExitOnForwardFailure=yes",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
        ]

        if cfg.strict_host_key_checking:
            base += ["-o", "StrictHostKeyChecking=yes"]
        else:
            base += ["-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null"]

        return base

    async def _read_stderr(self, proc: asyncio.subprocess.Process):
        if not proc.stderr:
            return
        try:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    return
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                async with self._lock:
                    self._status.last_error = text
                logger.info(f"proxy ssh: {text}")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.debug(f"proxy stderr reader error: {e}")

    async def _monitor_loop(self):
        while True:
            async with self._lock:
                desired = self._desired_running
                cfg = self._config

            if not desired:
                return
            if not cfg or not cfg.enabled:
                async with self._lock:
                    self._status.status = "disabled"
                return

            backoff = min(60, max(1, 2 ** min(6, self._status.retry_count)))

            try:
                if not _is_port_available("127.0.0.1", cfg.server_listen_port):
                    raise OSError(f"PORT_IN_USE: 127.0.0.1:{cfg.server_listen_port}")

                cmd = self._build_ssh_command(cfg)
                async with self._lock:
                    self._status.status = "connecting"
                    self._status.listen_port = cfg.server_listen_port
                    self._status.target = f"127.0.0.1:{cfg.center_proxy_port}"
                    self._status.last_error = None

                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.PIPE,
                )

                async with self._lock:
                    self._proc = proc
                    self._status.pid = proc.pid

                self._stderr_task = asyncio.create_task(self._read_stderr(proc))

                await asyncio.sleep(0.5)
                if proc.returncode is None:
                    async with self._lock:
                        self._status.status = "connected"
                        self._status.connected_since = _utc_now_iso()
                        self._status.retry_count = 0
                        self._status.last_error = None
                    logger.info("proxy connected")

                rc = await proc.wait()
                async with self._lock:
                    if self._desired_running:
                        self._status.status = "error"
                        self._status.last_error = self._status.last_error or f"ssh exited with code {rc}"
                        self._status.retry_count += 1
                        self._status.pid = None
                        self._status.connected_since = None
                        self._proc = None

                if not self._desired_running:
                    return
                logger.warning(f"proxy disconnected (rc={rc}), retry in {backoff}s")
                await asyncio.sleep(backoff)
            except asyncio.CancelledError:
                return
            except Exception as e:
                async with self._lock:
                    self._status.status = "error"
                    self._status.last_error = str(e)
                    self._status.retry_count += 1
                    self._status.pid = None
                    self._status.connected_since = None
                    self._proc = None

                if not self._desired_running:
                    return
                logger.warning(f"proxy start failed: {e}, retry in {backoff}s")
                await asyncio.sleep(backoff)


_manager: Optional[ProxyForwarderManager] = None


def get_proxy_manager() -> ProxyForwarderManager:
    global _manager
    if _manager is None:
        _manager = ProxyForwarderManager()
    return _manager

