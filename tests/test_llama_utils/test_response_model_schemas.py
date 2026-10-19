"""Every response_model the pipeline hands to instructor builds a schema (O-06).

instructor 1.3.7 raises ``TypeError: issubclass() arg 1 must be a class`` on
``X | None`` fields at request time, which no other unit test reaches because
the fakes never go through ``openai_schema``.
"""

import instructor
import pytest
from instructor.process_response import handle_response_model

from reasoning_sub_agents.execution_synthesiser.document_composer import (
    ComposerResponse,
    ConsolidationResponse,
)
from reasoning_sub_agents.oracle.tools import ExecutorTurn, OracleAnswer
from reasoning_sub_agents.schemas import BooleanResponse, DecomposeItem


@pytest.mark.parametrize(
    'model',
    [
        BooleanResponse,
        ComposerResponse,
        ConsolidationResponse,
        ExecutorTurn,
        OracleAnswer,
        list[DecomposeItem],
    ],
    ids=lambda m: str(m).rsplit('.', 1)[-1].rstrip("'>"),
)
def test_response_model_builds(model):
    # The same call instructor's patched create() makes before any request.
    handle_response_model(
        model,
        mode=instructor.Mode.JSON,
        messages=[{'role': 'user', 'content': 'x'}],
    )
