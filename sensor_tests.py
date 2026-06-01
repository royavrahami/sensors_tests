import concurrent.futures
import json
import logging
import os
from datetime import datetime

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader

from ssh_utils import load_sensor_details, run_ssh_command

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv(dotenv_path=os.getenv("SENSORZ_ENV_PATH", os.path.join("config", ".env")))

sensors_file_path = os.getenv('SENSOR_DETAILS_PATH')
reports_directory = os.getenv('REPORTS_DIRECTORY')
password_sensorz = os.getenv('SSH_PASSWORD')

assert sensors_file_path is not None, "SENSOR_DETAILS_PATH is not set"
assert reports_directory is not None, "REPORTS_DIRECTORY is not set"
assert password_sensorz is not None, "SSH_PASSWORD is not set"

print("Environment variables loaded successfully.")


def load_tests(file_path):
    assert os.path.isfile(file_path), "Test file {} does not exist.".format(file_path)
    with open(file_path) as file:
        tests = json.load(file)
        assert isinstance(tests, dict), "Tests file format is incorrect. Expected a dictionary."
        print("Test definitions loaded.")
        return tests


def run_test_on_sensor(sensor, tests):
    ip_address_sensor = sensor['ip_address_sensor']  # Correct key for IP address
    hostname_sensor = sensor['hostname']  # Assuming 'hostname' is correct
    username_sensorz = sensor['username_sensorz']  # Correct key for username
    Password_sensorz = sensor['Password_sensorz']  # Correct key for password, if individual password for each sensor

    sensor_result = {
        "hostname": hostname_sensor,
        "ip_address": ip_address_sensor,
        "results": {}
    }

    for category, test_commands in tests.items():
        category_results = []
        for test in test_commands:
            logging.info("Executing test: {} on sensor: {} {}".format(test['name'], hostname_sensor, ip_address_sensor))
            success, output = run_ssh_command(
                ip_address_sensor, username_sensorz, Password_sensorz, test['command'], use_sudo=True
            )
            test_status = "Passed" if success else "Failed"
            category_results.append({
                "test_name": test['name'],
                "output": output,
                "status": test_status
            })
        sensor_result["results"][category] = category_results

    logging.info("Tests completed for sensor: {} {}".format(hostname_sensor, ip_address_sensor))
    return sensor_result


def execute_tests(sensor_details, tests):
    """Execute tests on all sensors."""
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Map each sensor to the run_test_on_sensor function using its correct details.
        futures = {executor.submit(run_test_on_sensor, sensor, tests): sensor for sensor in sensor_details}
        test_results = [future.result() for future in concurrent.futures.as_completed(futures)]
    return test_results


def generate_html_report(test_results, title, template_dir='templates', template_file='report_template.html'):
    env = Environment(loader=FileSystemLoader(template_dir))
    template = env.get_template(template_file)
    report_data = {
        'title': title,
        'date_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'test_results': test_results
    }
    report_content = template.render(report_data)
    print("HTML report generated.")
    return report_content


def generate_report(report_content, report_filename=None):
    report_directory = os.getenv('REPORTS_DIRECTORY', 'reports')
    if not os.path.exists(report_directory):
        os.makedirs(report_directory)
    report_filepath = os.path.join(report_directory, report_filename if report_filename else 'report.html')
    with open(report_filepath, "w") as report_file:
        report_file.write(report_content)
    print(f"Report saved to: {report_filepath}")
    return report_filepath


load_dotenv(dotenv_path=os.getenv("SENSORZ_ENV_PATH", os.path.join("config", ".env")))


def main():
    print("Starting test execution...")
    sensor_details = load_sensor_details(os.getenv('SENSOR_DETAILS_PATH'))
    tests = load_tests(os.getenv('TESTS_DEFINITIONS_PATH'))
    test_results = execute_tests(sensor_details, tests)

    # Format the current date and time to include in the filename
    now = datetime.now()
    formatted_datetime = now.strftime("%Y-%m-%d_%H-%M-%S")  # This is the date and time format
    title = f'Sensor Test Report - {formatted_datetime}'  # This is your title
    report_filename = f"sensor_test_report_{formatted_datetime}.html"  # Custom report filename

    report = generate_html_report(test_results, title)
    report_filepath = generate_report(report, report_filename)

    logging.info("Report saved to {}".format(report_filepath))


if __name__ == "__main__":
    load_dotenv(dotenv_path=os.getenv("SENSORZ_ENV_PATH", os.path.join("config", ".env")))
    main()
