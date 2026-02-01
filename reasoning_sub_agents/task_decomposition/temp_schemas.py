from pydantic import BaseModel

from ..schemas import DecomposeItem


class DecomposeItemContainer(BaseModel):
    decompose_items: list[DecomposeItem]