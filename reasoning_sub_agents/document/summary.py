import json
import logging

from openai import OpenAI

from ..llama_utils import extract_content, generate_simple_llm_input, stream_conversation
from ..progress import llm_step
from ..prompt_budget import cap_prompt
from .models import Document

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """
You maintain a short rolling summary of a document that is being built from sub-tasks.

Previous summary (may be empty):
================================================================================
{old_summary}
================================================================================

Parts that changed in the latest compose step (id, kind, title, excerpt):
================================================================================
{changed}
================================================================================

Full document outline (id, kind, title, char_count):
================================================================================
{outline}
================================================================================

Write an updated summary of at most {max_words} words describing what the document now contains.
Return only the summary text, no preamble.
"""


def update_rolling_summary(
    document: Document,
    changed_part_ids: list[str],
    llm_client: OpenAI,
    *,
    max_words: int = 400,
    excerpt_chars: int = 400,
    prompt_token_budget: int = 16384,
) -> str:
    changed: list[dict] = []
    for part_id in changed_part_ids:
        if not document.has_part(part_id):
            changed.append({'id': part_id, 'status': 'deleted'})
            continue
        part = document.get_part(part_id)
        excerpt = part.body[:excerpt_chars]
        changed.append(
            {
                'id': part.id,
                'kind': part.kind,
                'title': part.title,
                'excerpt': excerpt,
            }
        )
    outline = [item.model_dump() for item in document.outline()]
    prompt = cap_prompt(
        SUMMARY_PROMPT.format(
            old_summary=document.summary or '(empty)',
            changed=json.dumps(changed, indent=2),
            outline=json.dumps(outline, indent=2),
            max_words=max_words,
        ),
        prompt_token_budget,
    )
    with llm_step('Rolling summary'):
        response = stream_conversation(
            llama_client=llm_client,
            llm_input=generate_simple_llm_input(prompt),
        )
    summary = extract_content(response)
    words = summary.split()
    if len(words) > max_words:
        summary = ' '.join(words[:max_words])
    document.summary = summary
    logger.info('updated rolling summary (%s words)', len(summary.split()))
    return summary
