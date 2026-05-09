from pydantic import BaseModel, Field
from typing import Annotated, Literal, Union

# TODO: appropriately credit cline for inspiration of the search and replace for the final result
#


write_text_description = """
The full result text that will replace the previous text in its entirety.
"""


class WriteResult(BaseModel):
    """
    If this is used, it will overwrite previously output modification such as `replace_in_text`.
    As such, there is no point to using `replace_in_text` before this.
    Ideally try to avoid using this unless it will greatly improve the synthesis output.
    """
    type: Literal['write']
    text: str = Field(..., description=write_text_description)


class AppendResult(BaseModel):
    """
    This will be used ot directly append to the result.
    """
    type: Literal['append']
    text: str = Field(..., description="text to append to the end of the result")


search_description = """
rules:
    * Use the exact right amount of lines in each `search` section to uniquely match each set of lines that need to change
    * Include *just* enough lines in each `search section to uniquely match each set of lines that need to change.
"""

replacement_text_description = """
    * To delete code: Use empty `replace` section`
"""


class ReplacePartResult(BaseModel):
    """
    This tool is to be used when replacing parts of text within the result.
    CRITICAL RULES:
    1. `search` MUST match exactly the text to be replaced
        * this means matching characters, whitespace, line endings and symbols EXACTLY!
    2. Only the first instance will be replaced
        * use multiple instances of this tool if more than one change is needed
        * when using multiple instances list them in order of change
    3. Keep search and replace blocks concise
        * break large `search`/`replace` blocks into a series of smaller blocks that each change a small part of the result
        * Include just the changing lines, and a few surrounding lines if needed for uniqueness.
         * Do not include long runs of unchanging lines in `search`/`replace` blocks.
         * Each line must be complete. Never truncate lines mid-way through as this can cause matching failures.
     4. Special operations:
         * To move code: Use two `search`/`replace` blocks (one to delete from original + one to insert at new location)
    """
    type: Literal['replace_in_text']
    search: str = Field(...,
                        description=search_description)
    replace: str = Field(..., description=replacement_text_description)



synthesis_content_description = """
Use this space when there is uncertainty about the next course of action.
It should contain the subjects of uncertainty and rationalise potential steps to overcome them.
"""


class SynthesisPlanning(BaseModel):
    """
    This is intended to be space to reason out future blocks
    """
    type: Literal['synthesis_planning']
    content: str = Field(..., description=synthesis_content_description)



synthesis_reset_content_description = """
Use this field to describe why a reset was needed
"""


class SynthesisReset(BaseModel):
    """
    During the course of generating steps to produce the final output, it may be discovered part way through that the steps are incorrect, a better way has been noticed or something else.
    Outputting this will result in all previous steps being discarded and only the steps after the last instance of this will take effect
    """
    type: Literal['synthesis_reset']
    content: str = Field(..., description=synthesis_reset_content_description)


DocumentSynthesisItems = Annotated[
    WriteResult | ReplacePartResult | SynthesisReset | AppendResult,
    Field(discriminator='type')
]