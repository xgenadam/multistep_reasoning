"""Package entry point (retired MCP server, S-002).

The original ``__main__`` re-exported ``mcp_server.main``. The MCP server was
retired in favor of the oobabooga extension, but the module was never removed
from the import, so ``python -m reasoning_sub_agents`` crashed on startup.

There is currently no first-party CLI entry point. Two supported ways to run
the orchestrator:

- oobabooga extension: ``oobabooga_extension/script.py`` (in-UI generation)
- headless harness:    ``dsh-podman-venv/bin/python journal/baseline/harness.py``
"""

import sys

if __name__ == '__main__':
    sys.stderr.write(
        'reasoning_sub_agents has no CLI entry point: the mcp_server module '
        'was retired (see journal/S-002.md). Use the oobabooga extension '
        '(oobabooga_extension/script.py) or the baseline harness '
        '(journal/baseline/harness.py).\n'
    )
    sys.exit(1)