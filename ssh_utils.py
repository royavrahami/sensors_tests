"""Shared SSH / connectivity helpers for the sensor test scripts.

Single source of truth for the primitives that were previously duplicated
(with subtle divergence) across ``check_ping_sensors.py``, ``sensor_tests.py``,
``check_sensors_tools_installed.py`` and ``detect_package_manager_and_install.py``.

All functions are side-effect-light and unit-tested (see tests/test_ssh_utils.py).
"""

from __future__ import annotations

import logging
import os
import socket
import subprocess

import paramiko
import yaml

logger = logging.getLogger(__name__)


def load_sensor_details(file_path: str) -> list[dict]:
    """Load the sensor inventory from a YAML file.

    Returns a list of sensor dicts, or an empty list if the file is missing
    or unreadable (callers iterate over the result).
    """
    try:
        with open(file_path) as fh:
            data = yaml.safe_load(fh)
        return data or []
    except FileNotFoundError:
        logger.error("Sensor inventory not found: %s", file_path)
        return []
    except Exception as exc:  # noqa: BLE001 - defensive: never crash on bad input
        logger.error("Failed to read sensor inventory %s: %s", file_path, exc)
        return []


def can_ping(ip_address: str, timeout: int = 10) -> tuple[bool, str]:
    """Ping a host once (cross-platform). Returns ``(success, output)``."""
    flag = "-n" if os.name == "nt" else "-c"
    cmd = ["ping", flag, "1", ip_address]
    try:
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout
        )
        return proc.returncode == 0, proc.stdout.decode(errors="replace").strip()
    except subprocess.TimeoutExpired:
        return False, "ping timed out"
    except Exception as exc:  # noqa: BLE001
        return False, f"ping failed: {exc}"


def can_connect(ip_address: str, port: int = 80, timeout: int = 30) -> bool:
    """Return True if a TCP connection to ``ip_address:port`` succeeds."""
    try:
        with socket.create_connection((ip_address, port), timeout=timeout):
            return True
    except OSError:
        return False


def update_ip_prefix(sensor: dict, new_prefix: str) -> dict:
    """Replace the first two octets of the sensor IP and return the sensor.

    The sensor dict is mutated in place and also returned for convenience.
    """
    parts = sensor["ip_address_sensor"].split(".")
    parts[0], parts[1] = new_prefix.split(".")[:2]
    sensor["ip_address_sensor"] = ".".join(parts)
    return sensor


def run_ssh_command(
    host: str,
    username: str,
    password: str,
    command: str,
    *,
    use_sudo: bool = False,
    timeout: int = 30,
) -> tuple[bool, str]:
    """Run a command on a host over SSH.

    Returns ``(success, output_or_error)``. When ``use_sudo`` is True the
    command is prefixed with ``sudo``.

    Note: uses Paramiko's ``AutoAddPolicy`` (trusts unknown host keys). For
    production use, switch to a pinned known-hosts policy.
    """
    if use_sudo:
        command = f"sudo {command}"
    try:
        with paramiko.SSHClient() as client:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=host, username=username, password=password, timeout=timeout)
            _stdin, stdout, stderr = client.exec_command(command)
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            if err:
                return False, err
            return True, out
    except Exception as exc:  # noqa: BLE001
        logger.error("SSH command failed on %s: %s", host, exc)
        return False, str(exc)
