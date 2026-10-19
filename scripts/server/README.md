# Server launchers

These start the host-side Devstral-123B llama-server on port 8000: the big model and the future judge (Phase Q). They run on the host, not in the container.
The container-side generator (Qwen-27B) is a separate server at `http://host.containers.internal:5000/v1`; point `LLM_BASE_URL` at it.
