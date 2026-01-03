from llama_cpp import Llama
from .schemas import UserQueryHistory


class HistoryManager:
    def __init__(self):
        self.history = []
        self.init
