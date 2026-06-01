import concurrent.futures
import logging
import os
import re
import yaml
from dotenv import load_dotenv
import paramiko

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv(dotenv_path=r'config/.env')
sensors_file_path = os.getenv('SENSOR_DETAILS_PATH')
PASSWORD_SENSORZ = os.getenv('PASSWORD_SENSORZ')


def load_sensor_details(file_path: str):
    """Load sensor details from YAML file."""
    try:
        with open(file_path) as file:
            return yaml.safe_load(file)
    except FileNotFoundError as e:
        logging.error(f"Error loading sensor details: {e}")
        return []
    except Exception as e:
        logging.error(f"Error reading the file: {e}")
        return []


def run_ssh_command(ip_address_sensor: str, username_sensorz: str, sensorz_password: str, command: str):
    """Execute an SSH command on the sensor."""
    try:
        with paramiko.SSHClient() as client:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(hostname=ip_address_sensor, username=username_sensorz, password=sensorz_password)
            _, stdout, stderr = client.exec_command(command)
            stdout_content = stdout.read().decode() if stdout else ''
            stderr_content = stderr.read().decode() if stderr else ''
            return stdout_content, stderr_content
    except Exception as e:
        logging.error(f"SSH command execution failed for {ip_address_sensor}: {e}")
        return '', str(e)


def detect_package_manager_and_install(ip_address_sensor: str, username_sensorz: str, sensorz_password: str, tool: str):
    """Detect the package manager and install the required tool."""
    apt_check_command = "which apt"
    stdout, _ = run_ssh_command(ip_address_sensor, username_sensorz, sensorz_password, apt_check_command)
    if stdout.strip():
        install_command = f"sudo apt-get update && sudo apt-get install {tool} -y"
    else:
        install_command = f"sudo yum makecache fast && sudo yum install {tool} -y"
    stdout, stderr = run_ssh_command(ip_address_sensor, username_sensorz, sensorz_password, install_command)
    if stderr.strip():
        logging.error(f"Error installing {tool} on {ip_address_sensor}: {stderr}")
    return stderr


def process_sensor(sensor: dict):
    """Process each sensor for checking and installing tools and performing ping test."""
    ip_address_sensor = sensor['ip_address_sensor']
    username_sensorz = sensor['username_sensorz']
    hostname = sensor.get('hostname', 'Unknown Hostname')

    tools_to_check = ['stress', 'iperf3', 'mtr', 'dnsutils']
    installed_tools = []
    already_installed = []
    failed_to_install = []

    for tool in tools_to_check:
        stdout, _ = run_ssh_command(ip_address_sensor, username_sensorz, PASSWORD_SENSORZ, f'which {tool}')
        if stdout.strip():
            already_installed.append(tool)
            logging.info(f"{hostname} ({ip_address_sensor}): {tool} - already installed")
        else:
            stderr = detect_package_manager_and_install(ip_address_sensor, username_sensorz, PASSWORD_SENSORZ, tool)
            if 'is already the newest version' in stderr or 'newly installed' in stderr:
                installed_tools.append(tool)
                logging.info(f"{hostname} ({ip_address_sensor}): {tool} - installed")
            else:
                failed_to_install.append(tool)
                logging.error(f"{hostname} ({ip_address_sensor}): {tool} - failed to install")

    # Perform ping test
    logging.info(f"{hostname} ({ip_address_sensor}): Starting ping test")
    stdout, _ = run_ssh_command(ip_address_sensor, username_sensorz, PASSWORD_SENSORZ, 'ping -c 4 8.8.8.8')
    ping_results = re.search(r'--- 8.8.8.8 ping statistics ---\n(.*)', stdout, re.DOTALL)
    ping_output = ping_results.group(1).strip() if ping_results else 'Ping test failed'

    summary = f"\nSummary of Operations for {ip_address_sensor} ({hostname}):\n" \
              f"  Installed in this cycle: {', '.join(installed_tools) or 'None'}\n" \
              f"  Already installed: {', '.join(already_installed) or 'None'}\n" \
              f"  Failed to install: {', '.join(failed_to_install) or 'None'}\n" \
              f"  Ping test: {'Successful' if '0% packet loss' in ping_output else 'Failed'}\n" \
              f"  Ping output: {ping_output}\n"
    return summary


def main():
    sensor_details = load_sensor_details(sensors_file_path)
    if not sensor_details:
        logging.error("No sensor details found.")
        return

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [executor.submit(process_sensor, sensor) for sensor in sensor_details]
        summaries = [future.result() for future in concurrent.futures.as_completed(futures)]

    # Print summaries after collecting all of them
    for summary in summaries:
        print(summary)


if __name__ == "__main__":
    main()
