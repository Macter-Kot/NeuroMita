from enum import Enum, auto


class LaptopEvents(Enum):
    """События связанные с ноутбуком"""
    TOUCH_LAPTOP = auto()  # Игрок взял ноутбук
    FIND_BUTTON = auto()  # Игрок нашел кнопку
    PRESS_BUTTON = auto()  # Игрок нажал кнопку


class LockboxEvents(Enum):
    """События связанные с сейфом"""
    TOUCH_LOCKBOX_BUTTON = auto()  # Касание кнопки сейфа
    TYPING_CODE = auto()  # Игрок вводит код дальше
    WRONG_CODE = auto()  # Игрок ввел неправильный код
    CORRECT_CODE = auto()  # Игрок ввел правильный код


class PlayerEvents(Enum):
    """События связанные с игроком"""
    # События ноутбука
    TOUCH_LAPTOP = LaptopEvents.TOUCH_LAPTOP
    FIND_BUTTON = LaptopEvents.FIND_BUTTON
    PRESS_BUTTON = LaptopEvents.PRESS_BUTTON

    # События сейфа
    TOUCH_LOCKBOX_BUTTON = LockboxEvents.TOUCH_LOCKBOX_BUTTON
    TYPING_CODE = LockboxEvents.TYPING_CODE
    WRONG_CODE = LockboxEvents.WRONG_CODE
    CORRECT_CODE = LockboxEvents.CORRECT_CODE

    # Прочие события
    TRY_TO_KILL_MITA = auto()
    KISS_MITA = auto()
