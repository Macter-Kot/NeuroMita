from abc import ABC, abstractmethod

from FSM.Events.MitaEvents import MitaEvents
from FSM.Events.PlayerEvents import PlayerEvents

import re
from promptPart import PromptPart, PromptType


class BaseState(ABC):
    """Абстрактный класс для состояний"""

    def __init__(self, prompts=None, sub_state=None):
        if prompts is None:
            prompts = []
        self._prompts = prompts
        self._sub_state = sub_state

    @abstractmethod
    def on_enter(self) -> None:
        """Вызывается при входе в состояние"""
        pass

    @abstractmethod
    def on_exit(self) -> None:
        """Вызывается при выходе из состояния"""
        pass

    @abstractmethod
    def handle_event(self, event: MitaEvents | PlayerEvents) -> 'BaseState':
        """Обработка событий, возвращает State"""
        pass

    #region ProcessingLogic

    def process_response(self, message_text):
        """Вычленяет команды из текста, а затем в соответствии с этим реагирует"""
        if self._sub_state:
            self._sub_state.process_response(message_text)

        commands = self.get_commands(message_text)
        self.process_commands(commands)
        self.process_vars()

    @abstractmethod
    def process_vars(self):
        """
        Смотрим на переменные, и думаем, нужно ли что-то делать
        :return:
        """

    @abstractmethod
    def process_commands(self, commands):
        """
        Каждый нулевой элемент каждой команды - тег
        :param commands:
        :return:
        """
        pass

    def get_commands(self, message_text, split='|'):
        """
        Получает массив команд (в каждой массив параметров).
        Каждая команда — это список, где первый элемент — тег, остальные — параметры.
        :param message_text: Текст сообщения, содержащий команды.
        :param split: Разделитель параметров внутри тега.
        :return: Список команд (списков параметров).
        """
        commands = []
        pattern = re.compile(r"<([^>]+)>(.*?)</\1>", re.DOTALL)  # Регулярное выражение для поиска тегов

        # Ищем все совпадения в message_text
        matches = pattern.finditer(message_text)

        for match in matches:
            # Извлекаем тег и содержимое
            tag = match.group(1).strip()
            content = match.group(2).strip()

            # Разделяем строку на отдельные значения
            params = [tag] + [x.strip() for x in content.split(split)]

            # Добавляем команду в список
            commands.append(params)

        return commands

    #endregion

    def get_prompts_text(self, prompt_type: PromptType = PromptType.FIXED_START):
        combined_text = ""
        if self._prompts:
            prompts = [prompt for prompt in self._prompts if prompt.type == prompt_type]
            for prompt in prompts:
                if prompt.active:
                    combined_text += str(prompt)+"\n"

            if self._sub_state:
                combined_text += self._sub_state.get_prompts_text()

        return combined_text

    def get_variables_text(self):
        """
        Возвращает рекурсивно переменные текстом, для того чтобы их знала Мита
        :return: text
        """
        text = self.get_current_variables_text()
        if self._sub_state:
            text += self._sub_state.get_variables_text()

        return text


    @abstractmethod
    def get_current_variables_text(self):
        """
        Возвращает переменные текстом, для того чтобы их знала Мита
        :return: text
        """

