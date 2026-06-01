"""Unit tests for the shared ssh_utils helpers (no real network/SSH)."""

from __future__ import annotations

import subprocess


import ssh_utils


# ── load_sensor_details ──────────────────────────────────────────────────────

def test_load_sensor_details_reads_yaml_list(tmp_path):
    f = tmp_path / "sensors.yml"
    f.write_text(
        "- hostname: s1\n  ip_address_sensor: 10.8.0.10\n  username_sensorz: admin\n",
        encoding="utf-8",
    )
    sensors = ssh_utils.load_sensor_details(str(f))
    assert isinstance(sensors, list)
    assert sensors[0]["ip_address_sensor"] == "10.8.0.10"


def test_load_sensor_details_missing_file_returns_empty():
    assert ssh_utils.load_sensor_details("/no/such/file.yml") == []


def test_load_sensor_details_empty_file_returns_empty(tmp_path):
    f = tmp_path / "empty.yml"
    f.write_text("", encoding="utf-8")
    assert ssh_utils.load_sensor_details(str(f)) == []


# ── update_ip_prefix ─────────────────────────────────────────────────────────

def test_update_ip_prefix_replaces_first_two_octets():
    sensor = {"ip_address_sensor": "10.8.0.123"}
    result = ssh_utils.update_ip_prefix(sensor, "10.3")
    assert result["ip_address_sensor"] == "10.3.0.123"
    assert sensor["ip_address_sensor"] == "10.3.0.123"  # mutated in place


# ── can_ping ─────────────────────────────────────────────────────────────────

def test_can_ping_success(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=0, stdout=b"1 received", stderr=b"")

    monkeypatch.setattr(ssh_utils.subprocess, "run", fake_run)
    ok, output = ssh_utils.can_ping("10.8.0.10")
    assert ok is True
    assert "received" in output


def test_can_ping_failure(monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout=b"100% loss", stderr=b"")

    monkeypatch.setattr(ssh_utils.subprocess, "run", fake_run)
    ok, _ = ssh_utils.can_ping("10.8.0.99")
    assert ok is False


def test_can_ping_timeout(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 10)

    monkeypatch.setattr(ssh_utils.subprocess, "run", fake_run)
    ok, output = ssh_utils.can_ping("10.8.0.10")
    assert ok is False
    assert "timed out" in output


# ── can_connect ──────────────────────────────────────────────────────────────

def test_can_connect_success(monkeypatch):
    class _Sock:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(ssh_utils.socket, "create_connection", lambda *a, **k: _Sock())
    assert ssh_utils.can_connect("10.8.0.10", 22) is True


def test_can_connect_failure(monkeypatch):
    def boom(*a, **k):
        raise OSError("refused")

    monkeypatch.setattr(ssh_utils.socket, "create_connection", boom)
    assert ssh_utils.can_connect("10.8.0.10", 22) is False


# ── run_ssh_command ──────────────────────────────────────────────────────────

class _FakeChannel:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data


class _FakeSSHClient:
    last_command = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def set_missing_host_key_policy(self, policy):
        pass

    def connect(self, **kwargs):
        pass

    def exec_command(self, command):
        _FakeSSHClient.last_command = command
        return None, _FakeChannel(b"ok-output"), _FakeChannel(b"")


def test_run_ssh_command_success(monkeypatch):
    monkeypatch.setattr(ssh_utils.paramiko, "SSHClient", _FakeSSHClient)
    ok, output = ssh_utils.run_ssh_command("10.8.0.10", "admin", "pw", "uptime")
    assert ok is True
    assert output == "ok-output"
    assert _FakeSSHClient.last_command == "uptime"


def test_run_ssh_command_uses_sudo(monkeypatch):
    monkeypatch.setattr(ssh_utils.paramiko, "SSHClient", _FakeSSHClient)
    ssh_utils.run_ssh_command("10.8.0.10", "admin", "pw", "apt update", use_sudo=True)
    assert _FakeSSHClient.last_command == "sudo apt update"


def test_run_ssh_command_reports_stderr(monkeypatch):
    class _ErrClient(_FakeSSHClient):
        def exec_command(self, command):
            return None, _FakeChannel(b""), _FakeChannel(b"permission denied")

    monkeypatch.setattr(ssh_utils.paramiko, "SSHClient", _ErrClient)
    ok, output = ssh_utils.run_ssh_command("10.8.0.10", "admin", "pw", "reboot")
    assert ok is False
    assert "permission denied" in output


def test_run_ssh_command_handles_connection_error(monkeypatch):
    class _BoomClient(_FakeSSHClient):
        def connect(self, **kwargs):
            raise OSError("unreachable")

    monkeypatch.setattr(ssh_utils.paramiko, "SSHClient", _BoomClient)
    ok, output = ssh_utils.run_ssh_command("10.8.0.10", "admin", "pw", "uptime")
    assert ok is False
    assert "unreachable" in output
