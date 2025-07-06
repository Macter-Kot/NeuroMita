from typing import Any
from .base import Tool

class CalculatorTool(Tool):
    name = "calculator"
    description = "Выполняет простые арифметические выражения. Пример: 2+2*5"
    parameters = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Арифметическое выражение, допускающее + - * / и скобки"
            }
        },
        "required": ["expression"]
    }

    def run(self, expression: str, **_) -> Any:
        try:
            # ⚠️ eval в продакшн лучше заменить безопасным парсером.
            result = eval(expression, {"__builtins__": {}})
            return str(result)
        except Exception as e:
            return f"Ошибка калькулятора: {e}"