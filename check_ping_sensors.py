import concurrent.futures
import logging
import os
import subprocess
from datetime import datetime
from functools import wraps

import paramiko
import yaml
from dotenv import load_dotenv

# Initialize a list to track unreachable sensors.
sensor_status = []
total_sensors_tested = 0

# Setup logging to display informational messages and timestamps.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from the specified .env file.
load_dotenv(dotenv_path=r'config/.env')
sensors_file_path = os.getenv('SENSOR_DETAILS_PATH')
password_sensorz = os.getenv('PASSWORD_SENSORZ')

# Ensure that both required environment variables are set.
assert sensors_file_path and password_sensorz, "Required environment variables are not set."


def load_sensor_details(file_path: str) -> dict:
    """Load sensor details from a YAML file."""
    with open(file_path) as file:
        return yaml.safe_load(file)


def can_ping(ip_address: str) -> bool:
    """Check if an IP address is reachable using ping."""
    response = subprocess.run(['ping', '-c', '1', ip_address], stdout=subprocess.PIPE)
    return response.returncode == 0


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
            updated_sensor = update_ip_prefix(sensor, new_prefix=new_prefix)
            if can_ping(updated_sensor['ip_address_sensor']):
                try:
                    return f(updated_sensor, *args, **kwargs)
                except Exception as second_try_error:
                    logging.error(f"Retry attempt failed for {updated_sensor['ip_address_sensor']}: {second_try_error}")
            else:
                logging.error(f"IP {updated_sensor['ip_address_sensor']} is not pingable.")
            sensor_status.append({
                'hostname': sensor.get('hostname', 'Unknown hostname'),
                'original_ip': original_ip,
                'updated_ip': updated_sensor['ip_address_sensor'],
                'reason': 'Failed to ping after IP update'
            })
            return None

    return wrapper_retry


def update_ip_prefix(sensor: dict, new_prefix: str) -> dict:
    parts = sensor['ip_address_sensor'].split('.')
    parts[0], parts[1] = new_prefix.split('.')[:2]
    sensor['ip_address_sensor'] = '.'.join(parts)
    return sensor


@retry
def ping_test(sensor: dict) -> dict:
    """Execute a ping test from a sensor."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=sensor['ip_address_sensor'], username=sensor['username_sensorz'],
                   password=password_sensorz, timeout=20)
    stdin, stdout, stderr = client.exec_command("ping -c 4 8.8.8.8")
    output = stdout.read().decode()
    ping_status = "Pass" if "4 packets transmitted, 4 received" in output else "Failed"
    client.close()
    return {
        'hostname': sensor.get('hostname', 'Unknown'),
        'ip': sensor['ip_address_sensor'],
        'ping_status': ping_status,
        'output': output
    }


def execute_tests(sensor_details: list) -> dict:
    """Execute ping tests and handle results."""
    results = {'Passed': [], 'Failed': []}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(ping_test, sensor): sensor for sensor in sensor_details}
        for future in concurrent.futures.as_completed(futures):
            var = futures[future]
            result = future.result()
            if result:
                results['Passed' if result['ping_status'] == 'Pass' else 'Failed'].append(result)

    # Include sensors that failed to ping after IP update
    results['Failed'].extend(sensor_status)

    return results


def save_report(test_results, report_path):
    """Save the test results to a specified file."""
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"{report_path}/Ping_Test_Report_{timestamp}.yaml"
    with open(filename, 'w') as file:
        yaml.safe_dump(test_results, file)
    logging.info(f"Report saved to {filename}")


def main():
    """Main function to load sensor details and execute tests."""
    print("Starting connection and ping tests...")
    sensor_details = load_sensor_details(sensors_file_path)
    test_results = execute_tests(sensor_details)

    print("\nTest summary:")
    print(f"Total sensors tested: {len(sensor_details)}")
    print(f"Sensors Passed All Tests: {len(test_results['Passed'])}")
    print(f"Sensors Failed The Test: {len(test_results['Failed'])}")

    # Display details of sensors that passed and failed in the console
    for status in ['Passed', 'Failed']:
        print(f"\nSensors that {status.lower()}:")
        for sensor in test_results[status]:
            print(f"Hostname: {sensor.get('hostname')}, IP: {sensor.get('ip')}, Status: {sensor.get('ping_status')}")

    report_path = os.getenv("PING_REPORTS_DIRECTORY", "reports")
    save_report(test_results, report_path)


if __name__ == "__main__":
    main()
