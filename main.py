import os
import subprocess
import sys

print(f"Using Python interpreter: {sys.executable}")

# Resolve sibling scripts relative to this file so the project is portable
# regardless of the checkout location or current working directory.
HERE = os.path.dirname(os.path.abspath(__file__))


def run_script(script_path):
    python_executable = sys.executable  # Gets the Python interpreter path currently running the script
    result = subprocess.run([python_executable, script_path], capture_output=True, text=True)
    print('STDOUT:', result.stdout)
    print('STDERR:', result.stderr)


def main():
    scripts = [
        os.path.join(HERE, 'check_ping_sensors.py'),
        os.path.join(HERE, 'detect_package_manager_and_install.py'),
        os.path.join(HERE, 'sensor_tests.py'),
    ]

    for script in scripts:
        print(f"Running script: {script}")
        run_script(script)


if __name__ == '__main__':
    main()
