from contextlib import contextmanager
from typing import Callable, Union, ContextManager

from llama_cpp import Llama, LlamaState

from .schemas import LlamaResponse


LlamaRunner = Callable[[str, Union[LlamaState, None], Union[float, None]], LlamaResponse]


@contextmanager
def llama_manager(llm: Llama, state: Union[LlamaState, None] = None) -> ContextManager[Llama]:
    """Context manager to temporarily manage and restore Llama model states."""
    # current_state = llm.save_state()
    # llm.reset()
    if state is not None:
        llm.load_state(state)
        pass

    try:
        yield llm
    finally:
        pass
        # llm.load_state(current_state)


def llama_container(
    llm: Llama, **default_kwargs
) -> LlamaRunner:
    """Factory function to create a Llama runner with preset model and temperature."""

    def llama_runner(
        prompt: str,
        state: Union[LlamaState, None] = None,
        temperature: Union[float, None] = None,
        **kwargs
    ) -> LlamaResponse:
        """Run a chat completion on the Llama model with the given prompt and state."""
        effective_kwargs = {**default_kwargs, **kwargs}
        if temperature is not None:
            effective_kwargs["temperature"] = temperature

        with llama_manager(llm, state) as managed_llm:
            llama_response = managed_llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": prompt},
                ],
                **effective_kwargs,
            )
            return LlamaResponse(**llama_response)

    return llama_runner
