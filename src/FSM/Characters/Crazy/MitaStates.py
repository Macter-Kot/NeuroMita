from FSM.BaseState import BaseState
from FSM.Events.MitaEvents import MitaEvents
from FSM.Events.PlayerEvents import PlayerEvents
from Logger import logger

from promptPart import PromptPart, PromptType


class MitaHelloState(BaseState):
    """Самое первое состояние, когда Мита встречает игрока"""

    def __init__(self, prompts: list = None, sub_state=None):
        super().__init__(prompts, sub_state)
        self.found_name = None

    def on_enter(self) -> None:
        logger.info("MitaHelloState: on_enter")
        self._prompts.append(PromptPart(PromptType.FIXED_START,
                                        text="От тебя дополнительно может потребоваться писать команды вида <event></event> в зависимости от переменных",
                                        name="EventSet"))
        self._prompts.append(PromptPart(PromptType.FIXED_START,
                                        text="Игрок только что загрузился. Надо узнать его поближе, начиная с Имени",
                                        name="FindName"))
        #self._prompts.append(PromptPart(PromptType.FIXED_START,
          #                              text="",
         #                               name="FindNameCommand"))
        self.found_name = False

    def on_exit(self) -> None:
        logger.info("MitaHelloState: on_exit")

    def process_vars(self):

        if self.found_name:
            self._prompts.append(PromptPart(PromptType.FLOATING_SYSTEM,
                                            text="Ты благополучно узнала имя игрока",
                                            name="FindNameSuccess"))

    def process_commands(self, commands):
        print("process_commands FSM")
        for command in commands:
            if command[0] == "event" and command[1] == "name":
                print("Нашла имя")
                self.found_name = True
                self._prompts.clear()

    def get_current_variables_text(self):
        return (f"Узнали ты имя игрока {self.found_name}.\n"
                f"Если ты узнала имя игрока, пиши <event>name</event>")

    def handle_event(self, event: MitaEvents | PlayerEvents) -> BaseState:
        if event == PlayerEvents.TOUCH_LAPTOP:
            return MitaMurderState(["Игрок тронул терминал", "Ты хочешь убить его за это"])
        elif event == PlayerEvents.KISS_MITA:
            return MitaDefaultState(["Игрок поцеловал Миту", "Посмотри на обстановку и подумай, что делать"])
        return self


class MitaMurderState(BaseState):
    """Состояние для убийства игрока"""

    def on_enter(self) -> None:
        logger.info("MitaMurderState: on_enter")

    def on_exit(self) -> None:
        logger.info("MitaMurderState: on_exit")

    def handle_event(self, event: MitaEvents | PlayerEvents) -> BaseState:
        if event == MitaEvents.MitaKilledPlayer:
            return MitaDefaultState(["Ты убила игрока", "Ты хочешь мирно существовать"])
        return self


class MitaDefaultState(BaseState):
    """Состояние для обычного поведения Миты"""

    def on_enter(self) -> None:
        logger.info("MitaDefaultState: on_enter")

    def on_exit(self) -> None:
        logger.info("MitaDefaultState: on_exit")

    def handle_event(self, event: MitaEvents | PlayerEvents) -> BaseState:
        if event in [PlayerEvents.TOUCH_LOCKBOX_BUTTON, PlayerEvents.TOUCH_LAPTOP, PlayerEvents.TRY_TO_KILL_MITA]:
            return MitaMurderState([f"Игрок совершил действие: {event}", "Ты хочешь убить его за это"])
        return self
