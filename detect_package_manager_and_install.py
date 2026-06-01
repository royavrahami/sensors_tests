import logging
import os
from functools import wraps

import concurrent.futures  # Corrected import
import paramiko
from dotenv import load_dotenv

from ssh_utils import can_ping, load_sensor_details, update_ip_prefix

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Paramiko logging. Use INFO (not DEBUG) so transcripts with host keys,
# negotiated ciphers and internal IPs are never written to disk, and route
# the log to a gitignored path so it is never committed.
os.makedirs('logs', exist_ok=True)
paramiko.util.log_to_file(os.path.join('logs', 'paramiko.log'), level='INFO')

# Load environment variables
load_dotenv(dotenv_path=r'config/.env')
sensors_file_path = os.getenv('SENSOR_DETAILS_PATH')
SSH_PASSWORD = os.getenv('SSH_PASSWORD')


def retry(f):
    """Decorator to retry sensor operations with an updated IP address."""

    @wraps(f)
    def wrapper_retry(sensor, *args, **kwargs):
        try:
            return f(sensor, *args, **kwargs)
        except Exception as e:
            logging.error(f"First attempt failed for {sensor['ip_address_sensor']}: {e}")
            original_ip = sensor['ip_address_sensor']
            new_prefix = '10.3' if original_ip.startswith('10.8') else '10.8'
            update_ip_prefix(sensor, new_prefix)
            if can_ping(sensor['ip_address_sensor'])[0]:  # Check if the ping after update is successful
                try:
                    return f(sensor, *args, **kwargs)
                except Exception as second_try_error:
                    logging.error(f"Retry attempt failed for {sensor['ip_address_sensor']}: {second_try_error}")
                    return f"Failed operation on {sensor['ip_address_sensor']}: {second_try_error}"
            else:
                logging.error(f"IP {sensor['ip_address_sensor']} is not pingable after update.")
                return f"IP {sensor['ip_address_sensor']} is not reachable."

    return wrapper_retry


def run_ssh_command(ip_address_sensor: str, username_sensorz: str, password_sensorz: str, command: str) -> tuple:
    """Execute an SSH command on the sensor and return the output and error message if any."""
    logging.info(f"Attempting to execute SSH command on {ip_address_sensor}: {command}")
    try:
        with paramiko.SSHClient() as client:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=ip_address_sensor, username=username_sensorz, password=password_sensorz, timeout=30)
            stdin, stdout, stderr = client.exec_command(command)
            stdout_result = stdout.read().decode()
            stderr_result = stderr.read().decode()
            logging.info(f"STDOUT: {stdout_result}")
            if stderr_result:
                logging.error(f"STDERR: {stderr_result}")
                return stdout_result, f"SSH command error: {stderr_result}"
            return stdout_result, "Success"
    except paramiko.SSHException as e:
        error_message = f"SSH operation failed: {e}"
        logging.error(error_message)
        return '', error_message


def is_tool_installed(ip_address_sensor: str, username_sensorz: str, password_sensorz: str, tool: str) -> bool:
    """Check if a specific tool is installed on the sensor."""
    stdout, stderr = run_ssh_command(ip_address_sensor, username_sensorz, password_sensorz, f"which {tool}")
    installed = bool(stdout.strip())
    logging.info(f"{tool} installation status on {ip_address_sensor}: {'Installed' if installed else 'Not installed'}")
    return installed


def list_upgradable_packages(ip_address_sensor: str, username_sensorz: str, password_sensorz: str) -> tuple:
    """List upgradable packages on the sensor and return the output."""
    return run_ssh_command(ip_address_sensor, username_sensorz, password_sensorz,
                           "sudo apt update && apt list --upgradable")


def ensure_tool_installed(ip_address_sensor: str, username_sensorz: str, password_sensorz: str, tool: str) -> str:
    """Ensure a tool is installed on the sensor, installing it if necessary."""
    if not is_tool_installed(ip_address_sensor, username_sensorz, password_sensorz, tool):
        return install_tool(ip_address_sensor, username_sensorz, password_sensorz, tool)
    return "Already installed"


def install_tool(ip_address_sensor: str, username_sensorz: str, password_sensorz: str, tool: str) -> str:
    """Install a tool using apt-get and return the status."""
    stdout, stderr = run_ssh_command(ip_address_sensor, username_sensorz, password_sensorz,
                                     f"sudo apt install {tool} -y")
    if 'newly installed' in stdout or 'already the newest version' in stdout:
        return "Installed"
    elif stderr:
        return f"Failed to install {tool}: {stderr}"
    return "Installation failed with no specific error"


def parse_upgradable_packages(upgradable_output: str) -> list:
    """Extract package names from the apt list upgradable output."""
    lines = upgradable_output.split('\n')
    return [line.split('/')[0] for line in lines if line and not line.startswith('Listing...')]


def process_sensor(sensor: dict) -> str:
    """Process each sensor for updates, tool checks, installations, and a ping test."""
    ip_address_sensor = sensor['ip_address_sensor']
    username_sensorz = sensor['username_sensorz']
    password_sensorz = SSH_PASSWORD
    logging.info(f"Processing sensor at {ip_address_sensor}")
    ping_success, ping_output = can_ping(ip_address_sensor)
    if not ping_success:
        return f"Failed to ping {ip_address_sensor}: {ping_output}"
    upgradable_output, update_errors = list_upgradable_packages(ip_address_sensor, username_sensorz, password_sensorz)
    upgradable_packages = parse_upgradable_packages(upgradable_output)
    tools_to_check = ['stress', 'iperf3', 'mtr', 'dnsutils']
    installed_tools, already_installed, failed_to_install = [], [], []
    for tool in tools_to_check:
        result = ensure_tool_installed(ip_address_sensor, username_sensorz, password_sensorz, tool)
        if "Installed" in result:
            installed_tools.append(tool)
        elif "Already installed" in result:
            already_installed.append(tool)
        else:
            failed_to_install.append(f"{tool} {result.split(' ')[-1]}")
    summary = (
        f"\nSummary For Sensor: {ip_address_sensor}\n"
        f"Hostname: {sensor.get('hostname', 'Unknown Hostname')}\n"
        f"Issues: {'; '.join([update_errors if update_errors else 'No issues during update.'])}\n"
        f"Upgradable Packages: {', '.join(upgradable_packages) if upgradable_packages else 'No packages to upgrade.'}\n"
        f"Installed Tools: {', '.join(installed_tools) if installed_tools else 'None'}\n"
        f"Already Installed Tools: {', '.join(already_installed) if already_installed else 'None'}\n"
        f"Failed Installations: {', '.join(failed_to_install) if failed_to_install else 'None'}\n"
        f"Ping Test: {'Successful' if ping_success else 'Failed'}\n"
        f"Ping Output: {ping_output}\n"
    )
    return summary


def main():
    sensor_details = load_sensor_details(sensors_file_path)
    if not sensor_details:
        logging.error("No sensor details found.")
        return
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_sensor, sensor) for sensor in sensor_details]
        summaries = [future.result() for future in futures]
    for summary in summaries:
        print(summary)


if __name__ == "__main__":
    main()
