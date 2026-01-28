import logging
import subprocess
import time
from threading import Thread

import requests

logger = logging.getLogger(__name__)

# Global to track the running process (useful for potential future shutdown)
_server_process: subprocess.Popen | None = None


def _server_log_reader(process: subprocess.Popen):
    """Background thread to stream server logs via logging.info."""
    try:
        for line in process.stdout:
            if line:
                logger.info("Server: %s", line.rstrip())
    except Exception as e:
        logger.error("Error reading server logs: %s", e)


def start_llama_server(config: dict) -> None:
    """
    Starts the llama.cpp server based on the provided config dict,
    waits for it to be ready by polling /v1/models, and streams its logs via logging.info.

    This function does NOT create or return a client.
    Use create_llama_client() separately after calling this function.

    Raises RuntimeError/TimeoutError on failure.
    """
    global _server_process

    if _server_process is not None and _server_process.poll() is None:
        logger.warning("Server process is already running – skipping restart.")
        return

    # Build the full command list
    command = config["positional_args"][:]  # Copy list
    for flag, value in config["key_word_args"].items():
        command.append(flag)
        command.append(str(value))

    logger.info("Starting llama.cpp server...")
    logger.info("Full command: %s", " ".join(command))

    # Launch server in background
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    _server_process = process

    # Stream logs in a daemon thread
    Thread(target=_server_log_reader, args=(process,), daemon=True).start()

    # Extract host and port from config
    host = config["key_word_args"].get("--host", "127.0.0.1")
    port_str = config["key_word_args"].get("--port")
    if port_str is None:
        process.terminate()
        raise ValueError("--port not specified in config['key_word_args']")

    try:
        port = int(port_str)
    except ValueError:
        process.terminate()
        raise ValueError(f"Invalid --port value: {port_str}")

    base_url = f"http://{host}:{port}"
    models_url = f"{base_url}/v1/models"

    logger.info("Waiting for server to become ready at %s...", base_url)

    timeout_seconds = 600  # Adjust if your model loads slower
    poll_interval = 2
    start_time = time.time()

    while True:
        if time.time() - start_time > timeout_seconds:
            process.terminate()
            raise TimeoutError(
                f"Server did not become ready within {timeout_seconds} seconds")

        if process.poll() is not None:
            raise RuntimeError(
                "Server process exited unexpectedly during startup (check logs)")

        try:
            resp = requests.get(models_url, timeout=5)
            if resp.status_code == 200:
                import pdb; pdb.set_trace()
                logger.info("Server is ready!")
                logger.debug("Models response: %s", resp.json())
                return
        except (requests.ConnectionError, requests.Timeout):
            pass

        time.sleep(poll_interval)
