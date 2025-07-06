from abc import ABC, abstractmethod
from typing import Any, Dict


class Tool(ABC):
    """ Базовый интерфейс любого инструмента """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def description(self) -> str:
        """ Короткое описание – LLM увидит его в JSON ‑описании. """

    @property
    def parameters(self) -> Dict[str, Any]:
        """
        JSON-Schema входных параметров (OpenAI-style).
        Для Gemini/DeepSeek он тоже подходит.
        """
        return {}

    @abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Непосредственно выполняет действие инструмента,
        возвращает строку (или dict – на ваше усмотрение).
        """