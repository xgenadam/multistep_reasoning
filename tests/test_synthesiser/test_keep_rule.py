"""D-030: the keep rule as a setting (verbatim default, names, off) and the
compose fallback."""
from unittest.mock import patch

import pytest

from reasoning_sub_agents.document import AddPart, Document, DocumentApplyError, UpdatePart, check_payload
from reasoning_sub_agents.document.errors import DocumentIntegrityError
from reasoning_sub_agents.document.integrity import defined_names
from reasoning_sub_agents.execution_synthesiser.document_composer import (
    COMPOSE_PROMPT,
    RULE_ONE,
    ComposerResponse,
    DocumentComposer,
)
from tests.mock_openai import MockOpenAI
from tests.test_synthesiser.test_document_composer import _sub_task

JSON = 'reasoning_sub_agents.execution_synthesiser.document_composer.get_streamed_json_response'
RESULT = '```python\ndef parse(s):\n    return s.split()\n\n\ndef count(s):\n    return len(parse(s))\n```'


def _doc_with(body, part_id='wc.py'):
    doc = Document.empty()
    doc.apply([AddPart(id=part_id, kind='file', title=part_id, body=body)])
    return doc


def test_defined_names_reads_fenced_code():
    assert defined_names(RESULT) == ['parse', 'count']
    assert defined_names('class A:\n    pass\nasync def b(): pass') == ['A', 'b']


def test_names_allows_a_refactor_that_keeps_every_name():
    refactored = 'def parse(s):\n    return s.split()\n\ncount = None\ndef count(s):\n    return len(parse(s))\n'
    doc = _doc_with(refactored)
    ops = [AddPart(id='wc.py', kind='file', title='wc.py', body=refactored)]
    with pytest.raises(DocumentIntegrityError):
        check_payload(doc, ops, RESULT, 'verbatim')  # not an exact copy
    stats = check_payload(doc, ops, RESULT, 'names')
    assert stats['names_missing'] == [] and stats['keep_rule'] == 'names'


def test_names_fails_on_a_dropped_function_and_on_broken_code():
    doc = _doc_with('def parse(s):\n    return s.split()\n')
    ops = [AddPart(id='wc.py', kind='file', title='wc.py', body='x')]
    with pytest.raises(DocumentIntegrityError, match='count'):
        check_payload(doc, ops, RESULT, 'names')
    broken = _doc_with('def parse(s):\n    return s.split(\ndef count(s): pass\n')
    with pytest.raises(DocumentIntegrityError, match='does not parse'):
        check_payload(broken, ops, RESULT, 'names')


def test_off_enforces_nothing_and_logs_coverage():
    doc = _doc_with('def parse(s):\n    return s.split()\n')
    stats = check_payload(doc, [UpdatePart(id='wc.py', body='x')], RESULT, 'off')
    assert stats == {'keep_rule': 'off', 'coverage': 0.5}  # 2 of 4 code lines kept


def test_rule_one_differs_only_off_the_default():
    assert 'Do not re-type the sub-task result' in RULE_ONE['verbatim']
    assert 'refactor' in RULE_ONE['names'] and RULE_ONE['off'] == RULE_ONE['names']
    assert '{rule_one}' in COMPOSE_PROMPT


def test_fallback_keeps_the_result_instead_of_failing_the_turn():
    task = _sub_task('Write wc', RESULT)
    bad = ComposerResponse(ops=[AddPart(id='wc.py', kind='file', title='wc.py', body='def parse(s): pass')])
    for fallback in (False, True):
        composer = DocumentComposer(llm_client=MockOpenAI(), max_retries=2, keep_rule='names',
                                    compose_fallback=fallback)
        document = Document.empty()
        with patch(JSON) as mock_json:
            mock_json.side_effect = [bad, bad]
            if not fallback:
                with pytest.raises(DocumentApplyError, match='count'):
                    composer.compose('req', [task], task, document)
                continue
            composer.compose('req', [task], task, document)
        assert 'def count' in document.parts[0].body
        assert composer.history[-1]['attempt'] == 'fallback'
        assert 'count' in composer.history[-1]['fallback_after']


def test_options_and_registry_pass_the_rule():
    from reasoning_sub_agents.config.schema import OptionsConfig
    opts = OptionsConfig(keep_rule='names', compose_fallback=True)
    assert (opts.keep_rule, opts.compose_fallback) == ('names', True)
    assert (OptionsConfig().keep_rule, OptionsConfig().compose_fallback) == ('verbatim', False)
    with pytest.raises(ValueError):
        OptionsConfig(keep_rule='loose')
