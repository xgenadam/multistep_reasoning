# Hidden tests for task.py: BigCodeBench-Hard v0.1.4 BigCodeBench/592, the
# row's `test` field. Below the marker line it is unchanged.
#
# Adaptations (bench v1-std README, "Test adaptations"):
# 1. BigCodeBench executes the solution and this test code as one module,
#    solution first, so the tests use the solution's names (task_func, its
#    constants, the modules it imports) without importing them. Equivalent
#    here: the import lines of the task's `code_prompt` (the code the prompt
#    tells the model to start with), then `from task import *`.
# 2. Names that `from task import *` brings in and that pytest would collect
#    as tests (a test* function, a Test* class or a unittest.TestCase subclass
#    defined in task.py) are deleted, so a deliverable cannot add its own
#    tests to the count.
# 3. pytest (hidden_tests.py) runs the TestCases class; BigCodeBench runs it
#    with unittest. The test methods are the same.
import csv
import os
from datetime import datetime
from random import randint
from task import *  # noqa: F401,F403
import unittest as _bcb_unittest

for _bcb_name, _bcb_value in list(globals().items()):
    if getattr(_bcb_value, '__module__', None) == 'task' and (
            _bcb_name.lower().startswith('test')
            or (isinstance(_bcb_value, type) and issubclass(_bcb_value, _bcb_unittest.TestCase))):
        del globals()[_bcb_name]

# ---- BigCodeBench test code (unchanged) ----
import unittest
import os
import shutil
FILE_PATH = os.path.join(OUTPUT_DIR, 'sensor_data.csv')
class TestCases(unittest.TestCase):
    def tearDown(self):
        """Clean up any files created during the tests."""
        # Check and remove the expected file if it exists
        # if os.path.exists(FILE_PATH):
        #     os.remove(FILE_PATH)
        if os.path.exists(OUTPUT_DIR):
            shutil.rmtree(OUTPUT_DIR)
    def test_csv_file_creation(self):
        """Test if the CSV file is successfully created."""
        task_func(1)
        self.assertTrue(os.path.exists(FILE_PATH))
    def test_csv_file_rows(self):
        """Test if the CSV file contains the correct number of rows for 24 hours."""
        task_func(24)
        with open(FILE_PATH, 'r') as f:
            self.assertEqual(len(f.readlines()), 25)  # Including header
    def test_csv_file_header(self):
        """Test if the CSV file header matches the expected sensors."""
        task_func(0)
        with open(FILE_PATH, 'r') as f:
            reader = csv.reader(f)
            header = next(reader)
            self.assertEqual(header, ['Time', 'Temperature', 'Humidity', 'Pressure'])
    def test_file_path_return(self):
        """Test if the correct file path is returned."""
        file_path = task_func(1)
        self.assertEqual(file_path, FILE_PATH)
    def test_no_hours_data(self):
        """Test sensor data generation with 0 hours."""
        task_func(0)
        with open(FILE_PATH, 'r') as f:
            self.assertEqual(len(f.readlines()), 1)  # Only header row expected
