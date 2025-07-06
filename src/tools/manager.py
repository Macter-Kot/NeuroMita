# tools/manager.py
from typing import Dict, List, Any
from .calc import CalculatorTool
from .web_read import WebPageReaderTool
from .web_search  import WebSearchTool
from .base        import Tool


class ToolManager:
    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self.register(CalculatorTool())
        self.register(WebSearchTool())
        self.register(WebPageReaderTool())   # ← регистрация

    # -------------------------------------------------
    #  Регистрация / базовая схема (OpenAI-style)
    # -------------------------------------------------
    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def json_schema(self) -> List[dict]:
        """OpenAI-style: [{name, description, parameters}, …]"""
        return [
            {
                "name":        t.name,
                "description": t.description,
                "parameters":  t.parameters
            } for t in self._tools.values()
        ]

    # -------------------------------------------------
    #  Универсальная «прослойка» для любого провайдера
    # -------------------------------------------------
    def get_tools_payload(self, model_name: str) -> List[dict]:
        """
        Возвращает tools-массив в формате,
        который понимает конкретная модель/провайдер.

        • OpenAI / DeepSeek / Anthropic  → [{name, …}] (как json_schema)
        • Gemini / Gemma                → [{functionDeclarations:[{name, …}]}]
        • остальные                     → пустой список
        """
        if not model_name:
            return []

        model_lower = model_name.lower()
        # Gemini-совместимые
        if "gemini" in model_lower or "gemma" in model_lower:
            return [{"functionDeclarations": self.json_schema()}]

        # OpenAI-совместимые
        if ("gpt" in model_lower or "deepseek" in model_lower
                or "claude" in model_lower or "mistral" in model_lower):
            return self.json_schema()

        # провайдер не поддерживает функции
        return []

    def run(self, name: str, arguments: dict):
        """
        Выполняет инструмент по имени и возвращает строковый результат.
        Если такого инструмента нет – возвращает сообщение об ошибке.
        """
        tool = self._tools.get(name)
        if not tool:
            return f"[Tool-Error] Неизвестный инструмент: {name}"

        # инструмент может ожидать **kwargs; если arguments=None, даём {}
        try:
            return tool.run(**(arguments or {}))
        except Exception as e:
            return f"[Tool-Error] {name} вызвал исключение: {e}"


def mk_tool_call_msg(name: str, args: dict):
    """
    Универсальный service-message: LLM → вызов инструмента.
    """
    return {
        "role": "assistant",
        "content": {          # важно: есть 'content', внутри объект
            "functionCall": {
                "name": name,
                "args": args or {}
            }
        }
    }


def mk_tool_resp_msg(name: str, result: str | dict):
    """
    Универсальный service-message: ответ инструмента → LLM.
    """
    return {
        "role": "tool",
        "content": {
            "functionResponse": {
                "name": name,
                "response": (result if isinstance(result, dict)
                             else {"result": result})
            }
        }
    }