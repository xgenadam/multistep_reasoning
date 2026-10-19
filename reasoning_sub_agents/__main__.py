"""Package entry point (retired MCP server, S-002).

The original ``__main__`` re-exported the MCP server's ``main``. The MCP server
was retired in favor of the oobabooga extension and removed in O-02; its tool
schema is archived in ``journal/archive/mcp-deep-reason-schema.md``.

There is currently no first-party CLI entry point. Two supported ways to run
the orchestrator:

- oobabooga extension: ``oobabooga_extension/script.py`` (in-UI generation)
- headless harness:    ``.venv/bin/python journal/baseline/harness.py``
"""

import sys

if __name__ == '__main__':
    sys.stderr.write(
        'reasoning_sub_agents has no CLI entry point: the MCP server was '
        'retired (see journal/archive/mcp-deep-reason-schema.md). Use the '
        'oobabooga extension (oobabooga_extension/script.py) or the baseline harness '
        '(journal/baseline/harness.py).\n'
    )
    sys.exit(1)