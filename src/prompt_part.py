from typing import Dict, List, Optional
import enum

from utils import load_text_from_file, shift_chars


class PromptType(enum.Enum):
    """Типы промптов."""
    FIXED_START = 1  # Фиксированный в начале
    FLOATING_SYSTEM = 2  # Плавающий системный - уходит и затухает в истории
    CONTEXT_TEMPORARY = 3  # Временный контекстный - перед сообщением, не сохраняется в историю


class PromptPart:
    """Класс для представления части промпта."""

    def __init__(self, part_type: PromptType, path: str = "", name=None, active=True, parameters: Optional[Dict] = None,
                 stride=0, text=""):
        """
        Инициализация части промпта.

        :param part_type: Тип промпта (из PromptType).
        :param path: путь к тексту промпта.
        :param parameters: Параметры для форматирования (опционально). // Надо бы сделать
        """
        self.name = name
        self.type = part_type
        self.text = text
        self.path = path
        self.active = active
        self.parameters = parameters or {}

        self.stride = stride

    def format(self, **kwargs) -> str:
        """Форматирует содержимое с параметрами как f-строка."""
        try:
            text = load_text_from_file(self.path)
            return text.format(**{**self.parameters, **kwargs})
        except KeyError as e:
            raise ValueError(f"Отсутствует параметр {e} в шаблоне промпта")

    @property
    def is_fixed(self) -> bool:
        """Проверяет, является ли промпт фиксированным в начале."""
        return self.type == PromptType.FIXED_START

    @property
    def is_floating(self) -> bool:
        """Проверяет, является ли промпт плавающим системным."""
        return self.type == PromptType.FLOATING_SYSTEM

    @property
    def is_temporary(self) -> bool:
        """Проверяет, является ли промпт временным контекстным."""
        return self.type == PromptType.CONTEXT_TEMPORARY

    def __str__(self) -> str:

        if self.path:
            text = load_text_from_file(self.path)
        else:
            text = self.text

        # Для секретной инфы... Да да, кто кодер вам все изи
        if self.stride != 0:
            text = shift_chars(text, self.stride)

        return text
