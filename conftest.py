"""Root conftest.py to ensure proper Python path for imports."""
import os
import sys

# Add the project root directory to sys.path so that imports work from tests
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
