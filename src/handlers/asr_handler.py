import time
import asyncio
import json
import sys
import os
import wave
from collections import deque
from threading import Lock
from io import BytesIO
import numpy as np

from typing import List, Union, Optional
from main_logger import logger
from utils.pip_installer import PipInstaller
from utils.gpu_utils import check_gpu_provider
from utils import getTranslationVariant as _

from handlers.asr_models.speech_recognizer_base import SpeechRecognizerInterface
from handlers.asr_models.google_recognizer import GoogleRecognizer
from handlers.asr_models.gigaam_recognizer import GigaAMRecognizer


from core.events import get_event_bus, Events


class AudioState:
    def __init__(self):
        self.is_recording = False
        self.audio_buffer = []
        self.last_sound_time = time.time()
        self.is_playing = False
        self.lock = asyncio.Lock()
        self.vc = None
        self.max_buffer_size = 9999999

    async def add_to_buffer(self, data):
        async with self.lock:
            if len(self.audio_buffer) >= self.max_buffer_size:
                self.audio_buffer = self.audio_buffer[-self.max_buffer_size // 2:]
            self.audio_buffer.append(data.copy())

audio_state = AudioState()


class SpeechRecognition:
    microphone_index = 0
    active = True
    _recognizer_type = "google"
    gigaam_model = "v2_rnnt"
    gigaam_device = "auto"
    gigaam_onnx_export_path = "SpeechRecognitionModels/GigaAM_ONNX"

    VOSK_SAMPLE_RATE = 16000
    CHUNK_SIZE = 512
    VAD_THRESHOLD = 0.5
    VAD_SILENCE_TIMEOUT_SEC = 1.0
    VAD_POST_SPEECH_DELAY_SEC = 0.2
    VAD_PRE_BUFFER_DURATION_SEC = 0.3

    FAILED_AUDIO_DIR = "FailedAudios"

    _text_lock = Lock()
    _text_buffer = deque(maxlen=15)
    _current_text = ""
    _is_processing_audio = asyncio.Lock()
    _is_running = False
    _recognition_task = None

    _torch = None
    _sd = None
    _np = None
    _silero_vad_loader = None
    _silero_vad_model = None
    
    _recognizer_instance: Optional[SpeechRecognizerInterface] = None
    _pip_installer = None
    _current_gpu = None

    @staticmethod
    def _show_install_warning(packages: list):
        package_str = ", ".join(packages)
        logger.warning("="*80)
        logger.warning(_(
            f"ВНИМАНИЕ: Для работы выбранного модуля распознавания речи требуются библиотеки: {package_str}.",
            f"WARNING: The selected speech recognition module requires libraries: {package_str}."
        ))
        logger.warning(_(
            "Сейчас начнется их автоматическая установка. Это может занять некоторое время.",
            "Automatic installation will now begin. This may take some time."
        ))
        logger.warning(_(
            "Также, после установки, будет загружена модель распознавания, которая может занимать до 1 ГБ дискового пространства.",
            "Also, after installation, a recognition model will be downloaded, which can take up to 1 GB of disk space."
        ))
        logger.warning("="*80)
        time.sleep(3)

    @staticmethod
    def _init_dependencies():
        if SpeechRecognition._pip_installer is None:
            try:
                SpeechRecognition._pip_installer = PipInstaller(
                    script_path=r"libs\python\python.exe",
                    libs_path="Lib",
                    update_log=logger.info
                )
                logger.info("PipInstaller успешно инициализирован.")
            except Exception as e:
                logger.error(f"Не удалось инициализировать PipInstaller: {e}", exc_info=True)
                return False
        
        if SpeechRecognition._recognizer_instance is None:
            if SpeechRecognition._recognizer_type == 'google':
                SpeechRecognition._recognizer_instance = GoogleRecognizer(
                    SpeechRecognition._pip_installer, logger
                )
            elif SpeechRecognition._recognizer_type == 'gigaam':
                recognizer = GigaAMRecognizer(SpeechRecognition._pip_installer, logger)
                recognizer.set_options(
                    device=SpeechRecognition.gigaam_device,
                    model=SpeechRecognition.gigaam_model,
                    onnx_path=SpeechRecognition.gigaam_onnx_export_path
                )
                SpeechRecognition._recognizer_instance = recognizer
        
        return True

    @staticmethod
    async def _init_vad_dependencies():
        try:
            if SpeechRecognition._torch is None:
                import torch
                SpeechRecognition._torch = torch
            if SpeechRecognition._sd is None:
                import sounddevice as sd
                SpeechRecognition._sd = sd
            if SpeechRecognition._np is None:
                import numpy as np
                SpeechRecognition._np = np
            if SpeechRecognition._silero_vad_loader is None:
                try:
                    from silero_vad import load_silero_vad
                except ImportError:
                    SpeechRecognition._show_install_warning(["silero-vad"])
                    SpeechRecognition._pip_installer.install_package(
                        ["silero-vad"], 
                        description=_("Установка Silero VAD...", "Installing Silero VAD...")
                    )
                    from silero_vad import load_silero_vad
                SpeechRecognition._silero_vad_loader = load_silero_vad
            
            if SpeechRecognition._silero_vad_model is None:
                model = SpeechRecognition._silero_vad_loader()
                SpeechRecognition._silero_vad_model = model
                logger.success("Модель Silero VAD успешно загружена.")
            
            return True
        except Exception as e:
            logger.error(f"Ошибка инициализации VAD зависимостей: {e}")
            return False

    @staticmethod
    def set_recognizer_type(recognizer_type: str = None):
        if recognizer_type in ["google", "gigaam"]:
            if SpeechRecognition._recognizer_instance:
                SpeechRecognition._recognizer_instance.cleanup()
                SpeechRecognition._recognizer_instance = None
            SpeechRecognition._recognizer_type = recognizer_type
            logger.info(f"Тип распознавателя установлен на: {recognizer_type}")
        else:
            logger.warning(f"Неизвестный тип распознавателя: {recognizer_type}. Используется 'google'.")

    @staticmethod
    def set_gigaam_options(device: str):
        SpeechRecognition.gigaam_device = device
        if SpeechRecognition._recognizer_instance and isinstance(SpeechRecognition._recognizer_instance, GigaAMRecognizer):
            SpeechRecognition._recognizer_instance.set_options(device=device)
        logger.info(f"Устройство для GigaAM установлено на: {device}")

    @staticmethod
    def check_model_installed(recognizer_type: str = None) -> bool:
        """Проверка установленности модели распознавания"""
        if recognizer_type is None:
            recognizer_type = SpeechRecognition._recognizer_type
            
        if recognizer_type == 'google':
            return True
        elif recognizer_type == 'gigaam':
            if not SpeechRecognition._init_dependencies():
                return False
            if SpeechRecognition._recognizer_instance:
                return SpeechRecognition._recognizer_instance.is_installed()
            return False
        return False
    
    @staticmethod
    async def install_model(recognizer_type: str = None) -> bool:
        """Установка модели распознавания"""
        if recognizer_type is None:
            recognizer_type = SpeechRecognition._recognizer_type
            
        if recognizer_type == 'google':
            return True
        elif recognizer_type == 'gigaam':
            if not SpeechRecognition._init_dependencies():
                return False
            if SpeechRecognition._recognizer_instance:
                return await SpeechRecognition._recognizer_instance.install()
            return False
        return False

    @staticmethod
    def receive_text() -> str:
        with SpeechRecognition._text_lock:
            result = " ".join(SpeechRecognition._text_buffer).strip()
            SpeechRecognition._text_buffer.clear()
            SpeechRecognition._current_text = ""
            return result

    @staticmethod
    def list_microphones():
        if SpeechRecognition._sd is None:
            try:
                import sounddevice as sd
                SpeechRecognition._sd = sd
            except ImportError:
                logger.error("Библиотека 'sounddevice' не найдена для вывода списка микрофонов.")
                return ["Ошибка: библиотека sounddevice не установлена"]
        
        try:
            devices = SpeechRecognition._sd.query_devices()
            input_devices = [dev['name'] for dev in devices if dev['max_input_channels'] > 0]
            return input_devices if input_devices else ["Микрофоны не найдены"]
        except Exception as e:
            logger.error(f"Не удалось получить список микрофонов: {e}")
            return [f"Ошибка: {e}"]

    @staticmethod
    async def handle_voice_message(recognized_text: str) -> None:
        text_clean = recognized_text.strip()
        if text_clean:
            event_bus = get_event_bus()
            event_bus.emit(Events.Speech.SPEECH_TEXT_RECOGNIZED, {'text': text_clean})

    @staticmethod
    async def live_recognition() -> None:
        max_retries = 3
        retry_count = 0
        
        try:
            while retry_count < max_retries and SpeechRecognition.active:
                try:
                    if not SpeechRecognition._init_dependencies():
                        logger.error("Не удалось инициализировать зависимости.")
                        return
                    
                    if not SpeechRecognition._recognizer_instance.is_installed():
                        logger.warning("ASR-модель не установлена. Остановлено распознавание.")
                        return
                        
                    if not await SpeechRecognition._recognizer_instance.init():
                        logger.error("Не удалось инициализировать распознаватель.")
                        return

                    retry_count = 0

                    if SpeechRecognition._recognizer_type == "google":
                        await SpeechRecognition._recognizer_instance.live_recognition(
                            SpeechRecognition.microphone_index,
                            SpeechRecognition.handle_voice_message,
                            None,
                            lambda: SpeechRecognition.active,
                            chunk_size=SpeechRecognition.CHUNK_SIZE
                        )
                    else:
                        if not await SpeechRecognition._init_vad_dependencies():
                            logger.error("Не удалось инициализировать VAD.")
                            return
                            
                        await SpeechRecognition._recognizer_instance.live_recognition(
                            SpeechRecognition.microphone_index,
                            SpeechRecognition.handle_voice_message,
                            SpeechRecognition._silero_vad_model,
                            lambda: SpeechRecognition.active,
                            sample_rate=SpeechRecognition.VOSK_SAMPLE_RATE,
                            chunk_size=SpeechRecognition.CHUNK_SIZE,
                            vad_threshold=SpeechRecognition.VAD_THRESHOLD,
                            silence_timeout=SpeechRecognition.VAD_SILENCE_TIMEOUT_SEC,
                            pre_buffer_duration=SpeechRecognition.VAD_PRE_BUFFER_DURATION_SEC
                        )
                        
                    break
                        
                except asyncio.CancelledError:
                    logger.info("Задача распознавания отменена.")
                    break
                except RuntimeError as e:
                    if "after shutdown" in str(e):
                        logger.warning("Попытка планирования future после shutdown loop. Игнорируем.")
                        break
                except Exception as e:
                    retry_count += 1
                    logger.error(f"Ошибка в цикле распознавания (попытка {retry_count}/{max_retries}): {e}", exc_info=True)
                    
                    if retry_count < max_retries and SpeechRecognition.active:
                        logger.info(f"Перезапуск через 2 секунды...")
                        await asyncio.sleep(2)
                    else:
                        logger.error("Превышено количество попыток перезапуска. Распознавание остановлено.")
                        break
        finally:
            SpeechRecognition._is_running = False
            logger.info("Цикл распознавания речи остановлен.")

    @staticmethod
    async def speech_recognition_start_async():
        await SpeechRecognition.live_recognition()

    @staticmethod
    def speech_recognition_start(device_id: int, loop):
        if SpeechRecognition._is_running:
            logger.info("Останавливаем текущее распознавание для запуска нового...")
            SpeechRecognition.speech_recognition_stop()
            time.sleep(0.5)

        SpeechRecognition._is_running = True
        SpeechRecognition.active = True
        SpeechRecognition.microphone_index = device_id
        SpeechRecognition._recognition_task = asyncio.run_coroutine_threadsafe(SpeechRecognition.speech_recognition_start_async(), loop)
        logger.info(f"Запущено распознавание речи на устройстве {device_id}")

    @staticmethod
    def speech_recognition_stop():
        if not SpeechRecognition._is_running:
            logger.debug("Распознавание речи уже остановлено.")
            return

        logger.info("Запрос на остановку распознавания речи...")
        SpeechRecognition.active = False

        task = SpeechRecognition._recognition_task
        if task and not task.done():
            task.cancel()
            logger.info(f"Задача распознавания речи {id(task)} помечена на отмену.")
        
        SpeechRecognition._is_running = False
        SpeechRecognition._recognition_task = None
        logger.info("Процедура остановки распознавания речи инициирована.")

    @staticmethod
    async def get_current_text() -> str:
        with SpeechRecognition._text_lock:
            return SpeechRecognition._current_text.strip()