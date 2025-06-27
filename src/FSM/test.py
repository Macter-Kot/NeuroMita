import asyncio

from Events.PlayerEvents import PlayerEvents
from FiniteStateMachine import FiniteStateMachine
from FSM.Characters.Crazy.MitaStates import MitaDefaultState, MitaMurderState, MitaHelloState


async def main():
    # Создаем список доступных состояний с правильными промптами
    available_states = [
        MitaDefaultState,
        MitaHelloState,
        MitaMurderState
    ]

    fsm = FiniteStateMachine(
        initial_state=MitaDefaultState(["Сейчас ты в обычном состоянии", "Ты хочешь мирно существовать"]),

    )

    fsm.handle_event(PlayerEvents.TOUCH_LAPTOP)  # MitaHelloState => MitaMurderState
    fsm.handle_event(PlayerEvents.FIND_BUTTON)  # MitaMurderState => ничего не происходит


if __name__ == "__main__":
    asyncio.run(main())
