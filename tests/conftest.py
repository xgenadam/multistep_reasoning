import pytest

from mock_openai import MockOpenAI


@pytest.fixture
def mock_openai_client():
    return MockOpenAI()