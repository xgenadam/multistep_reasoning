from unittest.mock import patch

import pytest

from reasoning_sub_agents.document import AddPart, Document
from reasoning_sub_agents.oracle import DocumentOracle, DocumentOracleError, OracleAnswer


def _doc_with_parts() -> Document:
    doc = Document.empty()
    doc.apply(
        [
            AddPart(
                id='chapter-1',
                kind='section',
                title='Chapter 1',
                body='Hermione found a wand of vine wood in the shop.',
            ),
            AddPart(
                id='src-main',
                kind='file',
                title='main.py',
                body='def greet():\n    return "hello"\n',
            ),
        ]
    )
    doc.summary = 'A story and a python file.'
    return doc


def test_list_read_search_and_summary():
    oracle = DocumentOracle(_doc_with_parts())
    parts = oracle.list_parts()
    assert [p['id'] for p in parts] == ['chapter-1', 'src-main']
    assert 'vine wood' in oracle.read_part('chapter-1')
    assert oracle.read_part('src-main', start=0, end=9) == 'def greet'
    hits = oracle.search('vine wood')
    assert len(hits) == 1
    assert hits[0].part_id == 'chapter-1'
    assert 'wand' in hits[0].excerpt
    file_hits = oracle.search('greet')
    assert file_hits[0].part_id == 'src-main'
    assert oracle.summary() == 'A story and a python file.'


def test_search_token_fallback():
    oracle = DocumentOracle(_doc_with_parts())
    hits = oracle.search('wand shop')
    assert hits[0].part_id == 'chapter-1'


def test_read_unknown_part_errors():
    oracle = DocumentOracle(Document.empty())
    with pytest.raises(DocumentOracleError, match='unknown part id'):
        oracle.read_part('missing')


def test_dispatch_read_and_search():
    oracle = DocumentOracle(_doc_with_parts())
    from reasoning_sub_agents.oracle import ListPartsTool, ReadPartTool, SearchTool

    payload = oracle.dispatch(
        [
            ListPartsTool(),
            ReadPartTool(id='chapter-1'),
            SearchTool(query='wand'),
        ]
    )
    assert 'chapter-1' in payload
    assert 'vine wood' in payload


def test_ask_uses_retrieved_excerpts():
    oracle = DocumentOracle(_doc_with_parts(), llm_client=object())
    with patch(
        'reasoning_sub_agents.oracle.document_oracle.get_streamed_json_response'
    ) as mock_json:
        mock_json.return_value = OracleAnswer(
            answer='Vine wood.', citations=['chapter-1']
        )
        answer = oracle.ask('What wand wood does Hermione have?')
    assert answer.answer == 'Vine wood.'
    assert answer.citations == ['chapter-1']
    prompt = mock_json.call_args.kwargs['llm_input'].messages[-1].content
    assert 'vine wood' in prompt.lower() or 'Vine wood' in prompt
