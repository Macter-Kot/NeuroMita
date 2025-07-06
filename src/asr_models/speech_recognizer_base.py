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
    
    @property
    def is_initialized(self) -> bool:
        return self._is_initialized