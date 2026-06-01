# sensors_tests

Parallel SSH health-check and diagnostics toolkit for a fleet of network
"sensor" devices. It connects to each device over SSH concurrently, runs
connectivity and tooling checks, and produces HTML/YAML reports.

> ⚠️ **Security note:** this tool connects to remote hosts over SSH. It reads
> credentials from a local `.env` file (never commit it) and writes its Paramiko
> log at `INFO` level into a git-ignored `logs/` directory. Do not lower the log
> level to `DEBUG` in a shared/committed context — DEBUG transcripts include host
> keys, negotiated ciphers and internal IPs.

## What it does

| Script | Purpose |
| ------ | ------- |
| `main.py` | Orchestrator — runs the checks below in sequence. |
| `check_ping_sensors.py` | Pings every device (with an IP-prefix failover retry) and reports which are unreachable. |
| `check_sensors_tools_installed.py` | Verifies that required diagnostic tools are present on each device. |
| `detect_package_manager_and_install.py` | Detects the device package manager and installs missing tools (`stress`, `iperf3`, `mtr`, `dnsutils`, …). |
| `sensor_tests.py` | Runs the test suite against each device and renders an HTML report from `sensor_report.html`. |
| `ssh_utils.py` | Shared, unit-tested SSH/ping/connectivity helpers used by all scripts. |

## Requirements

- Python 3.9+
- SSH reachability to the target devices
- Dependencies: `pip install -r requirements.txt`
  (`paramiko`, `PyYAML`, `python-dotenv`, `Jinja2`)

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create `config/.env` (git-ignored) with your settings:
   ```dotenv
   # SSH password used to authenticate to the devices
   SSH_PASSWORD=your-ssh-password

   # Path to the sensor inventory file (YAML/JSON)
   SENSOR_DETAILS_PATH=config/sensors.yml

   # Path to the test-definitions file
   TESTS_DEFINITIONS_PATH=config/tests.json

   # Where reports are written (defaults to ./reports)
   REPORTS_DIRECTORY=reports
   PING_REPORTS_DIRECTORY=reports
   ```

### Environment variables

| Variable | Required | Default | Description |
| -------- | :------: | ------- | ----------- |
| `SSH_PASSWORD` | ✅ | – | SSH password for the devices. |
| `SENSOR_DETAILS_PATH` | ✅ | – | Inventory file describing each device (hostname/IP). |
| `TESTS_DEFINITIONS_PATH` | ✅ | – | Test definitions consumed by `sensor_tests.py`. |
| `REPORTS_DIRECTORY` | ❌ | `reports` | Output directory for generated reports. |
| `PING_REPORTS_DIRECTORY` | ❌ | `reports` | Output directory for ping reports. |
| `SENSORZ_ENV_PATH` | ❌ | `config/.env` | Override the location of the `.env` file. |

## Usage

Run the full sequence:

```bash
python main.py
```

Or run an individual check:

```bash
python check_ping_sensors.py
python sensor_tests.py
```

## Testing

The shared SSH/ping/connectivity helpers in `ssh_utils.py` are unit-tested
(network calls are mocked — no real SSH/ping is performed):

```bash
pip install -r requirements.txt
pytest tests/ -q          # 13 tests
ruff check . --select F,E9
```

CI runs both on every push/PR (see `.github/workflows/quality.yml`).

## Notes / roadmap

- The SSH/ping/connectivity/inventory helpers were de-duplicated into the
  shared, tested `ssh_utils.py` module. Each script's `retry` decorator and
  `run_ssh_command` variants that have script-specific contracts remain local.
- Host-key handling uses an auto-add policy; switch to a pinned known-hosts
  policy for production use.

## License

MIT — see [LICENSE](LICENSE).
