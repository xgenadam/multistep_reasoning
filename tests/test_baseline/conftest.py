"""Load the journal/baseline scripts (not a package) as modules."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / 'journal' / 'baseline'
RUNS = BASELINE / 'runs'


def load_baseline_module(name: str):
    spec = importlib.util.spec_from_file_location(f'baseline_{name}', BASELINE / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve annotations here
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope='module')
def harness():
    return load_baseline_module('harness')


@pytest.fixture(scope='module')
def check():
    return load_baseline_module('check')


@pytest.fixture(scope='module')
def compare():
    return load_baseline_module('compare')
