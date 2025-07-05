from FSM.Events.MitaEvents import MitaEvents
from FSM.Events.PlayerEvents import PlayerEvents
from FSM.BaseState import BaseState
from main_logger import logger


class FiniteStateMachine:

    def __init__(self, initial_state: BaseState):
        self.current_state = initial_state

    def _set_state(self, state: BaseState) -> None:
        """Выполнить переход к указанному состоянию"""
        logger.info(f"Выходим из состояния: {self.current_state.__class__.__name__}")
        self.current_state.on_exit()

        self.current_state = state

        logger.info(f"Входим в состояние: {self.current_state.__class__.__name__}")
        self.current_state.on_enter()
        logger.info(f"Выполнен переход в состояние: {self.current_state.__class__.__name__}")

    def handle_event(self, event: MitaEvents | PlayerEvents) -> None:
        """Обработать событие"""
        new_state = self.current_state.handle_event(event)
        if new_state is not None and new_state != self.current_state:
            logger.info(f"Переход из {self.current_state.__class__.__name__} в {new_state.__class__.__name__}")
            self._set_state(new_state)

    def process_response(self, response):
        self.current_state.process_response(response)

    def get_prompts_text(self,prompt_type):
        return self.current_state.get_prompts_text(prompt_type)

    def get_variables_text(self):
        return self.current_state.get_variables_text()
