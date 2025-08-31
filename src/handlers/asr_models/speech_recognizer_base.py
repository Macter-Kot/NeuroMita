from abc import ABC, abstractmethod
from typing import Optional, List
import numpy as np

class SpeechRecognizerInterface(ABC):
    def __init__(self, pip_installer, logger):
        self.pip_installer = pip_installer
        self.logger = logger
        self._is_initialized = False

    @abstractmethod
    async def install(self) -> bool:
        pass

    @abstractmethod
    async def init(self, **kwargs) -> bool:
        pass

    @abstractmethod
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int) -> Optional[str]:
        pass

    @abstractmethod
    async def live_recognition(self, microphone_index: int, handle_voice_callback,
                               vad_model, active_flag, **kwargs) -> None:
        pass

    @abstractmethod
    def cleanup(self) -> None:
        pass

    @abstractmethod
    def is_installed(self) -> bool:
        pass

    # ===== Optional modular settings API (не обязательны к реализации) =====
    def settings_spec(self) -> List[dict]:
        """Вернуть схему полей настроек для UI. Пример:
        [
          {"key":"device", "label_ru":"Устройство", "label_en":"Device",
           "type":"combobox", "options":["auto","cuda","cpu","dml"], "default":"auto"}
        ]
        """
        return []

    def get_default_settings(self) -> dict:
        return {}

    def apply_settings(self, settings: dict) -> None:
        """Применить настройки на лету. По умолчанию ничего не делает."""
        return

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized