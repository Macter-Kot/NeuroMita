import asyncio
from typing import Optional
import numpy as np
from handlers.asr_models.speech_recognizer_base import SpeechRecognizerInterface
from utils import getTranslationVariant as _

class GoogleRecognizer(SpeechRecognizerInterface):
    def __init__(self, pip_installer, logger):
        super().__init__(pip_installer, logger)
        self._sr = None
        
    async def install(self) -> bool:
        try:
            import speech_recognition as sr
        except ImportError:
            self.logger.info("Библиотека 'SpeechRecognition' не найдена, попытка установки...")
            if self.pip_installer.install_package("SpeechRecognition", description="Установка SpeechRecognition..."):
                try:
                    import speech_recognition as sr
                except ImportError:
                    self.logger.critical("Не удалось импортировать 'SpeechRecognition' даже после установки.")
                    return False
            else:
                self.logger.critical("Не удалось установить 'SpeechRecognition'.")
                return False
        
        self._sr = sr
        return True
    
    async def init(self, **kwargs) -> bool:
        if self._sr is None:
            return False
        self._is_initialized = True
        return True
    
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int) -> Optional[str]:
        if not self._is_initialized:
            return None
            
        recognizer = self._sr.Recognizer()
        audio_data_int16 = (audio_data * 32767).astype(np.int16)
        
        audio = self._sr.AudioData(
            audio_data_int16.tobytes(),
            sample_rate=sample_rate,
            sample_width=2
        )
        
        try:
            text = recognizer.recognize_google(audio, language="ru-RU")
            return text
        except self._sr.UnknownValueError:
            return None
        except Exception as e:
            self.logger.error(f"Ошибка при распознавании Google: {e}")
            return None
    
    async def live_recognition(self, microphone_index: int, handle_voice_callback, 
                              vad_model, active_flag, **kwargs) -> None:
        if self._sr is None:
            self.logger.error("Модуль SpeechRecognition не инициализирован. Распознавание невозможно.")
            return

        recognizer = self._sr.Recognizer()
        google_sample_rate = 44100
        chunk_size = kwargs.get('chunk_size', 512)
        
        WaitTimeoutError = self._sr.WaitTimeoutError
        UnknownValueError = self._sr.UnknownValueError
        
        with self._sr.Microphone(device_index=microphone_index, sample_rate=google_sample_rate,
                               chunk_size=chunk_size) as source:
            mic_list = self._sr.Microphone.list_microphone_names()
            self.logger.info(f"Используется микрофон: {mic_list[microphone_index]}")
            recognizer.adjust_for_ambient_noise(source)
            self.logger.info("Скажите что-нибудь (Google)...")
            
            while active_flag():
                try:
                    audio = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: recognizer.listen(source, timeout=5)
                    )
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: recognizer.recognize_google(audio, language="ru-RU")
                    )
                    if text:
                        await handle_voice_callback(text)
                except WaitTimeoutError:
                    pass
                except UnknownValueError:
                    pass
                except Exception as e:
                    self.logger.error(f"Ошибка при распознавании Google: {e}")
                    break
    
    def cleanup(self) -> None:
        self._sr = None
        self._is_initialized = False