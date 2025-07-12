import io
import uuid
from win32 import win32gui
from audio_handler import AudioHandler
from main_logger import logger
from settings_manager import SettingsManager
from chat_model import ChatModel
from server import ChatServer
from telegram_handler import TelegramBotHandler

import gettext
from pathlib import Path
import os
import base64
import json
import glob
import sounddevice as sd
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS
from utils.ffmpeg_installer import install_ffmpeg

import asyncio
import threading
import binascii
import re
import subprocess
from utils import _
from utils import SH, process_text_to_voice
import sys

from screen_capture import ScreenCapture
import requests
import importlib
from local_voice import LocalVoice
import time
from asr_handler import SpeechRecognition
from utils.pip_installer import PipInstaller

import functools

from PyQt6.QtCore import QTimer, QObject, pyqtSignal
from PyQt6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QProgressBar

import tempfile, os

class TelegramAuthSignals(QObject):
    code_required = pyqtSignal(object)
    password_required = pyqtSignal(object)

class ChatController:
    def __init__(self, view):
        self.view = view
        
        self.voice_language_var = None
        self.local_voice_combobox = None
        self.debug_window = None
        self.mic_combobox = None

        self.ConnectedToGame = False
        self.chat_window = None
        self.token_count_label = None

        self.bot_handler = None
        self.bot_handler_ready = False

        self.selected_microphone = ""
        self.device_id = 0
        self.user_entry = None
        self.user_input = ""

        self.api_key = ""
        self.api_key_res = ""
        self.api_url = ""
        self.api_model = ""

        self.makeRequest = False
        self.api_hash = ""
        self.api_id = ""
        self.phone = ""

        try:
            target_folder = "Settings"
            os.makedirs(target_folder, exist_ok=True)
            self.config_path = os.path.join(target_folder, "settings.json")

            self.load_api_settings(False)
            self.settings = SettingsManager(self.config_path)
        except Exception as e:
            logger.info("Не удалось удачно получить из системных переменных все данные", e)
            self.settings = SettingsManager("Settings/settings.json")

        try:
            self.pip_installer = PipInstaller(
                script_path=r"libs\python\python.exe",
                libs_path="Lib",
                update_log=logger.info
            )
            logger.info("PipInstaller успешно инициализирован.")
        except Exception as e:
            logger.error(f"Не удалось инициализировать PipInstaller: {e}", exc_info=True)
            self.pip_installer = None

        self._check_and_perform_pending_update()

        self.local_voice = LocalVoice(self)
        self.voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")
        self.current_local_voice_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
        self.last_voice_model_selected = None
        if self.current_local_voice_id:
            for model_info in LOCAL_VOICE_MODELS:
                if model_info["id"] == self.current_local_voice_id:
                    self.last_voice_model_selected = model_info
                    break
        self.model_loading_cancelled = False

        self.model = ChatModel(self, self.api_key, self.api_key_res, self.api_url, self.api_model, self.makeRequest,
                               self.pip_installer)
        self.server = ChatServer(self, self.model)
        self.server_thread = None
        self.running = False
        self.start_server()

        self.textToTalk = ""
        self.textSpeaker = "/Speaker Mita"
        self.textSpeakerMiku = "/set_person CrazyMita"

        self.silero_turn_off_video = False
        self.dialog_active = False

        self.patch_to_sound_file = ""
        self.id_sound = -1
        self.instant_send = False
        self.waiting_answer = False

        self.lazy_load_batch_size = 50
        self.total_messages_in_history = 0
        self.loaded_messages_offset = 0
        self.loading_more_history = False

        self.staged_images = []
        self.attachment_label = None
        self.attach_button = None
        self.send_screen_button = None

        self.ffmpeg_install_popup = None
        QTimer.singleShot(100, self.check_and_install_ffmpeg)

        self.delete_all_sound_files()

        self.silero_connected = False
        self.game_connected_checkbox_var = False
        self.mic_recognition_active = False
        self.screen_capture_active = False
        self.camera_capture_active = False

        self.loop_ready_event = threading.Event()

        self.loop = None
        self.asyncio_thread = threading.Thread(target=self.start_asyncio_loop, daemon=True)
        self.asyncio_thread.start()

        self.auth_signals = TelegramAuthSignals()
        # self.auth_signals.code_required.connect(self.view.prompt_for_code)
        # self.auth_signals.password_required.connect(self.view.prompt_for_password)

        self.start_silero_async()

        initial_recognizer_type = self.settings.get("RECOGNIZER_TYPE", "google")
        initial_vosk_model = self.settings.get("VOSK_MODEL", "vosk-model-ru-0.10")

        SpeechRecognition.set_recognizer_type(initial_recognizer_type)
        SpeechRecognition.vosk_model = initial_vosk_model

        self.screen_capture_instance = ScreenCapture()
        self.screen_capture_thread = None
        self.screen_capture_running = False
        self.last_captured_frame = None
        self.image_request_thread = None
        self.image_request_running = False
        self.last_image_request_time = time.time()
        self.image_request_timer_running = False

        if self.settings.get("MIC_ACTIVE", False):
            SpeechRecognition.speech_recognition_start(self.device_id, self.loop)
            self.mic_recognition_active = True

        if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
            logger.info("Настройка 'ENABLE_SCREEN_ANALYSIS' включена. Автоматический запуск захвата экрана.")
            self.start_screen_capture_thread()

        if self.settings.get("ENABLE_CAMERA_CAPTURE", False):
            logger.info("Настройка 'ENABLE_CAMERA_CAPTURE' включена. Автоматический запуск захвата с камеры.")
            self.start_camera_capture_thread()

    def connect_view_signals(self):
        """Подключает сигналы к методам view после его создания"""
        self.auth_signals.code_required.connect(self.view.prompt_for_code)
        self.auth_signals.password_required.connect(self.view.prompt_for_password)

    def start_asyncio_loop(self):
        try:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            logger.info("Цикл событий asyncio успешно запущен.")
            self.loop_ready_event.set()
            try:
                self.loop.run_forever()
            except Exception as e:
                logger.info(f"Ошибка в цикле событий asyncio: {e}")
            finally:
                self.loop.close()
        except Exception as e:
            logger.info(f"Ошибка при запуске цикла событий asyncio: {e}")
            self.loop_ready_event.set()

    def start_silero_async(self):
        logger.info("Ожидание готовности цикла событий...")
        self.loop_ready_event.wait()
        if self.loop and self.loop.is_running():
            logger.info("Запускаем Silero через цикл событий.")
            asyncio.run_coroutine_threadsafe(self.startSilero(), self.loop)
        else:
            logger.info("Ошибка: Цикл событий asyncio не запущен.")

    async def startSilero(self):
        logger.info("Telegram Bot запускается!")
        try:
            if not self.api_id or not self.api_hash or not self.phone:
                logger.info("Ошибка: отсутствуют необходимые данные для Telegram бота")
                self.silero_connected = False
                return

            logger.info(f"Передаю в тг {SH(self.api_id)},{SH(self.api_hash)},{SH(self.phone)} (Должно быть не пусто)")

            self.bot_handler = TelegramBotHandler(self, self.api_id, self.api_hash, self.phone,
                                                  self.settings.get("AUDIO_BOT", "@silero_voice_bot"))

            try:
                await self.bot_handler.start()
                self.bot_handler_ready = True
                if hasattr(self, 'silero_connected') and self.silero_connected:
                    logger.info("ТГ успешно подключен")
                    self.update_status_colors()
                else:
                    logger.info("ТГ не подключен")
            except Exception as e:
                logger.info(f"Ошибка при запуске Telegram бота: {e}")
                self.bot_handler_ready = False
                self.silero_connected = False

        except Exception as e:
            logger.info(f"Критическая ошибка при инициализации Telegram Bot: {e}")
            self.silero_connected = False
            self.bot_handler_ready = False

    def get_speaker_text(self):
        if self.settings.get("AUDIO_BOT") == "@CrazyMitaAIbot":
            return self.textSpeakerMiku
        else:
            return self.textSpeaker

    async def run_send_and_receive(self, response, speaker_command, id=0):
        logger.info("Попытка получить фразу")
        self.waiting_answer = True
        await self.bot_handler.send_and_receive(response, speaker_command, id)
        self.waiting_answer = False
        logger.info("Завершение получения фразы")

    def check_text_to_talk_or_send(self):
        if bool(self.settings.get("SILERO_USE")) and self.textToTalk:
            self.voice_text()

        if self.image_request_timer_running:
            self.send_interval_image()

        if bool(self.settings.get("MIC_INSTANT_SENT")):
            if not self.waiting_answer:
                text_from_recognition = SpeechRecognition.receive_text()
                if text_from_recognition:
                    self.view.user_entry.insertPlainText(text_from_recognition)
                    self.user_input = self.view.user_entry.toPlainText().strip()
                    if not self.dialog_active:
                        self.send_instantly()

        elif bool(self.settings.get("MIC_ACTIVE")) and self.view.user_entry:
            text_from_recognition = SpeechRecognition.receive_text()
            if text_from_recognition:
                self.view.user_entry.insertPlainText(text_from_recognition)
                self.user_input = self.view.user_entry.toPlainText().strip()

    def send_interval_image(self):
        current_time = time.time()
        interval = float(self.settings.get("IMAGE_REQUEST_INTERVAL", 20.0))
        delta = current_time - self.last_image_request_time
        
        if delta >= interval:
            image_data = []
            if self.settings.get("ENABLE_SCREEN_ANALYSIS", False):
                logger.info(f"Отправка периодического запроса с изображением ({current_time - self.last_image_request_time:.2f}/{interval:.2f} сек).")
                history_limit = int(self.settings.get("SCREEN_CAPTURE_HISTORY_LIMIT", 1))
                frames = self.screen_capture_instance.get_recent_frames(history_limit)
                if frames:
                    image_data.extend(frames)
                    logger.info(f"Захвачено {len(frames)} кадров для периодической отправки.")
                else:
                    logger.info("Анализ экрана включен, но кадры не готовы или история пуста для периодической отправки.")

                if image_data:
                    if self.loop and self.loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            self.async_send_message(user_input="", system_input="", image_data=image_data),
                            self.loop)
                        self.last_image_request_time = current_time
                    else:
                        logger.error("Ошибка: Цикл событий не готов для периодической отправки изображений.")
                else:
                    logger.warning("Нет изображений для периодической отправки.")

    def voice_text(self):
        logger.info(f"Есть текст для отправки: {self.textToTalk} id {self.id_sound}")
        if self.loop and self.loop.is_running():
            try:
                self.voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")

                if self.voiceover_method == "TG":
                    logger.info("Используем Telegram (Silero/Miku) для озвучки")
                    asyncio.run_coroutine_threadsafe(
                        self.run_send_and_receive(self.textToTalk, self.get_speaker_text(), self.id_sound),
                        self.loop
                    )
                    self.textToTalk = ""

                elif self.voiceover_method == "Local":
                    selected_local_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
                    if selected_local_model_id:
                        logger.info(f"Используем {selected_local_model_id} для локальной озвучки")
                        if self.local_voice.is_model_initialized(selected_local_model_id):
                            asyncio.run_coroutine_threadsafe(
                                self.run_local_voiceover(self.textToTalk),
                                self.loop
                            )
                            self.textToTalk = ""
                        else:
                            logger.warning(f"Модель {selected_local_model_id} выбрана, но не инициализирована. Озвучка не будет выполнена.")
                            self.textToTalk = ""
                    else:
                        logger.warning("Локальная озвучка выбрана, но конкретная модель не установлена/не выбрана.")
                        self.textToTalk = ""
                else:
                    logger.warning(f"Неизвестный метод озвучки: {self.voiceover_method}")
                    self.textToTalk = ""

                logger.info("Выполнено")
            except Exception as e:
                logger.error(f"Ошибка при отправке текста на озвучку: {e}")
                self.textToTalk = ""
        else:
            logger.error("Ошибка: Цикл событий не готов.")

    def send_instantly(self):
        try:
            if self.ConnectedToGame:
                self.instant_send = True
            else:
                self.view.send_message()

            SpeechRecognition._text_buffer.clear()
            SpeechRecognition._current_text = ""
        except Exception as e:
            logger.info(f"Ошибка обработки текста: {str(e)}")

    def clear_user_input(self):
        self.user_input = ""
        self.view.user_entry.clear()

    def stage_image_bytes(self, img_bytes: bytes) -> int:
        """
        Сохраняет bytes изображения во временный *.png,
        добавляет путь в self.staged_images и возвращает
        текущее количество прикреплённых изображений.
        """
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="nm_clip_")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(img_bytes)

        self.staged_images.append(tmp_path)
        logger.info(f"Clipboard image staged: {tmp_path}")
        return len(self.staged_images)

    def clear_staged_images(self):
        """Очищает список прикреплённых изображений."""
        self.staged_images.clear()

    def start_server(self):
        if not self.running:
            self.running = True
            self.server.start()
            self.server_thread = threading.Thread(target=self.run_server_loop, daemon=True)
            self.server_thread.start()
            logger.info("Сервер запущен.")

    def stop_server(self):
        if self.running:
            self.running = False
            self.server.stop()
            logger.info("Сервер остановлен.")

    def run_server_loop(self):
        while self.running:
            needUpdate = self.server.handle_connection()
            if needUpdate:
                logger.info(f"[{time.strftime('%H:%M:%S')}] run_server_loop: Обнаружено needUpdate, вызываю load_chat_history.")
                QTimer.singleShot(0, self.view.load_chat_history)

    def _check_and_perform_pending_update(self):
        if not self.pip_installer:
            logger.warning("PipInstaller не инициализирован, проверка отложенного обновления пропущена.")
            return

        update_pending = self.settings.get("G4F_UPDATE_PENDING", False)
        target_version = self.settings.get("G4F_TARGET_VERSION", None)

        if update_pending and target_version:
            logger.info(f"Обнаружено запланированное обновление g4f до версии: {target_version}")
            package_spec = f"g4f=={target_version}" if target_version != "latest" else "g4f"
            description = f"Запланированное обновление g4f до {target_version}..."

            success = False
            try:
                success = self.pip_installer.install_package(
                    package_spec,
                    description=description,
                    extra_args=["--force-reinstall", "--upgrade"]
                )
                if success:
                    logger.info(f"Запланированное обновление g4f до {target_version} успешно завершено.")
                    try:
                        importlib.invalidate_caches()
                        logger.info("Кэш импорта очищен после запланированного обновления.")
                    except Exception as e_invalidate:
                        logger.error(f"Ошибка при очистке кэша импорта после обновления: {e_invalidate}")
                else:
                    logger.error(f"Запланированное обновление g4f до {target_version} не удалось (ошибка pip).")
            except Exception as e_install:
                logger.error(f"Исключение во время запланированного обновления g4f: {e_install}", exc_info=True)
                success = False

            finally:
                logger.info("Сброс флагов запланированного обновления g4f.")
                self.settings.set("G4F_UPDATE_PENDING", False)
                self.settings.set("G4F_TARGET_VERSION", None)
                self.settings.save_settings()
        else:
            logger.info("Нет запланированных обновлений g4f.")

    def update_game_connection(self, is_connected):
        self.ConnectedToGame = is_connected
        QTimer.singleShot(0, self.update_status_colors)

    def load_api_settings(self, update_model):
        logger.info("Начинаю загрузку настроек")

        if not os.path.exists(self.config_path):
            logger.info("Не найден файл настроек")
            return

        try:
            with open(self.config_path, "rb") as f:
                encoded = f.read()
            decoded = base64.b64decode(encoded)
            settings = json.loads(decoded.decode("utf-8"))

            self.api_key = settings.get("NM_API_KEY", "")
            self.api_key_res = settings.get("NM_API_KEY_RES", "")
            self.api_url = settings.get("NM_API_URL", "")
            self.api_model = settings.get("NM_API_MODEL", "")
            self.makeRequest = settings.get("NM_API_REQ", False)

            self.api_id = settings.get("NM_TELEGRAM_API_ID", "")
            self.api_hash = settings.get("NM_TELEGRAM_API_HASH", "")
            self.phone = settings.get("NM_TELEGRAM_PHONE", "")

            logger.info(f"Итого загружено {SH(self.api_key)},{SH(self.api_key_res)},{self.api_url},{self.api_model},{self.makeRequest} (Должно быть не пусто)")
            logger.info(f"По тг {SH(self.api_id)},{SH(self.api_hash)},{SH(self.phone)} (Должно быть не пусто если тг)")
            
            if update_model:
                if self.api_key:
                    self.model.api_key = self.api_key
                if self.api_url:
                    self.model.api_url = self.api_url
                if self.api_model:
                    self.model.api_model = self.api_model
                self.model.makeRequest = self.makeRequest
                self.model.update_openai_client()

            logger.info("Настройки загружены из файла")
        except Exception as e:
            logger.info(f"Ошибка загрузки: {e}")

    def all_settings_actions(self, key, value):
        if key in ["SILERO_USE", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            self.view.switch_voiceover_settings()

        if key == "SILERO_TIME":
            self.bot_handler.silero_time_limit = int(value)

        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                QMessageBox.information(self.view, "Информация",
                    "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)")

            if self.bot_handler:
                self.bot_handler.tg_bot = value

        elif key == "CHARACTER":
            self.model.current_character_to_change = value
            self.model.check_change_current_character()

        elif key == "NM_API_MODEL":
            self.model.api_model = value.strip()
        elif key == "NM_API_KEY":
            self.model.api_key = value.strip()
        elif key == "NM_API_URL":
            self.model.api_url = value.strip()
        elif key == "NM_API_REQ":
            self.model.makeRequest = bool(value)
        elif key == "gpt4free_model":
            self.model.gpt4free_model = value.strip()


        elif key == "MODEL_MAX_RESPONSE_TOKENS":
            self.model.max_response_tokens = int(value)
        elif key == "MODEL_TEMPERATURE":
            self.model.temperature = float(value)
        elif key == "MODEL_PRESENCE_PENALTY":
            self.model.presence_penalty = float(value)
        elif key == "MODEL_FREQUENCY_PENALTY":
            self.model.frequency_penalty = float(value)
        elif key == "MODEL_LOG_PROBABILITY":
            self.model.log_probability = float(value)
        elif key == "MODEL_TOP_K":
            self.model.top_k = int(value)
        elif key == "MODEL_TOP_P":
            self.model.top_p = float(value)
        elif key == "MODEL_THOUGHT_PROCESS":
            self.model.thinking_budget = float(value)



        elif key == "MODEL_MESSAGE_LIMIT":
            self.model.memory_limit = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_COUNT":
            self.model.max_request_attempts = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_TIME":
            self.model.request_delay = float(value)

        elif key == "MIC_ACTIVE":
            if bool(value):
                SpeechRecognition.speech_recognition_start(self.device_id, self.loop)
                self.mic_recognition_active = True
            else:
                SpeechRecognition.speech_recognition_stop()
                self.mic_recognition_active = False
            self.update_status_colors()

        elif key == "ENABLE_SCREEN_ANALYSIS":
            if bool(value):
                self.start_screen_capture_thread()
            else:
                self.stop_screen_capture_thread()
        elif key == "ENABLE_CAMERA_CAPTURE":
            if bool(value):
                self.start_camera_capture_thread()
            else:
                self.stop_camera_capture_thread()
        elif key in ["SCREEN_CAPTURE_INTERVAL", "SCREEN_CAPTURE_QUALITY", "SCREEN_CAPTURE_FPS",
                     "SCREEN_CAPTURE_HISTORY_LIMIT", "SCREEN_CAPTURE_TRANSFER_LIMIT", "SCREEN_CAPTURE_WIDTH",
                     "SCREEN_CAPTURE_HEIGHT"]:
            if self.screen_capture_instance and self.screen_capture_instance.is_running():
                logger.info(f"Настройка захвата экрана '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.stop_screen_capture_thread()
                self.start_screen_capture_thread()
            else:
                logger.info(
                    f"Настройка захвата экрана '{key}' изменена на '{value}'.")
        elif key == "SEND_IMAGE_REQUESTS":
            if bool(value):
                self.start_image_request_timer()
            else:
                self.stop_image_request_timer()
        elif key == "IMAGE_REQUEST_INTERVAL":
            if self.image_request_timer_running:
                logger.info(f"Настройка интервала запросов изображений изменена на '{value}'. ")
                self.stop_image_request_timer()
                self.start_image_request_timer()
            else:
                logger.info(
                    f"Настройка интервала запросов изображений изменена на '{value}'. Таймер не активен, изменения будут применены при следующем запуске.")
        elif key in ["EXCLUDE_GUI_WINDOW", "EXCLUDE_WINDOW_TITLE"]:
            exclude_gui = self.settings.get("EXCLUDE_GUI_WINDOW", False)
            exclude_title = self.settings.get("EXCLUDE_WINDOW_TITLE", "")

            hwnd_to_pass = None
            if exclude_gui:
                hwnd_to_pass = self.view.root.winfo_id()
                logger.info(f"Получен HWND окна GUI для исключения: {hwnd_to_pass}")
            elif exclude_title:
                try:
                    hwnd_to_pass = win32gui.FindWindow(None, exclude_title)
                    if hwnd_to_pass:
                        logger.info(f"Найден HWND для заголовка '{exclude_title}': {hwnd_to_pass}")
                    else:
                        logger.warning(f"Окно с заголовком '{exclude_title}' не найдено.")
                except Exception as e:
                    logger.error(f"Ошибка при поиске окна по заголовку '{exclude_title}': {e}")

            if self.screen_capture_instance:
                self.screen_capture_instance.set_exclusion_parameters(hwnd_to_pass, exclude_title,
                                                                      exclude_gui or bool(exclude_title))
                logger.info(
                    f"Параметры исключения окна переданы в ScreenCapture: exclude_gui={exclude_gui}, exclude_title='{exclude_title}'")

            if self.screen_capture_instance and self.screen_capture_instance.is_running():
                logger.info(f"Настройка исключения окна '{key}' изменена на '{value}'.")
                self.stop_screen_capture_thread()
                self.start_screen_capture_thread()
            else:
                logger.info(
                    f"Настройка исключения окна '{key}' изменена на '{value}'.")
        elif key == "RECOGNIZER_TYPE":
            SpeechRecognition.active = False
            time.sleep(0.1)

            SpeechRecognition.set_recognizer_type(value)

            if self.settings.get("MIC_ACTIVE", False):
                SpeechRecognition.active = True
                SpeechRecognition.speech_recognition_start(self.device_id, self.loop)
        elif key == "VOSK_MODEL":
            SpeechRecognition.vosk_model = value
        elif key == "SILENCE_THRESHOLD":
            SpeechRecognition.SILENCE_THRESHOLD = float(value)
        elif key == "SILENCE_DURATION":
            SpeechRecognition.SILENCE_DURATION = float(value)
        elif key == "VOSK_PROCESS_INTERVAL":
            SpeechRecognition.VOSK_PROCESS_INTERVAL = float(value)
        elif key == "IMAGE_QUALITY_REDUCTION_ENABLED":
            self.model.image_quality_reduction_enabled = bool(value)

            self.model.image_quality_reduction_start_index = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE":
            self.model.image_quality_reduction_use_percentage = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_MIN_QUALITY":
            self.model.image_quality_reduction_min_quality = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_DECREASE_RATE":
            self.model.image_quality_reduction_decrease_rate = int(value)

        elif key == "ENABLE_HISTORY_COMPRESSION_ON_LIMIT":
            self.model.enable_history_compression_on_limit = bool(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_PERIODIC":
            self.model.enable_history_compression_periodic = bool(value)
        elif key == "HISTORY_COMPRESSION_OUTPUT_TARGET":
            self.model.history_compression_output_target = str(value)
        elif key == "HISTORY_COMPRESSION_PERIODIC_INTERVAL":
            self.model.history_compression_periodic_interval = int(value)
        elif key == "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS":
            self.model.history_compression_min_messages_to_compress = float(value)

        if key == "CHAT_FONT_SIZE":
            try:
                font_size = int(value)
                self.view.update_chat_font_size(font_size)
                self.view.load_chat_history()
                logger.info(f"Размер шрифта чата изменен на: {font_size}. История перезагружена.")
            except ValueError:
                logger.warning(f"Неверное значение для размера шрифта чата: {value}")
            except Exception as e:
                logger.error(f"Ошибка при изменении размера шрифта чата: {e}")
        elif key == "SHOW_CHAT_TIMESTAMPS":
            self.view.load_chat_history()
            logger.info(f"Настройка 'Показывать метки времени' изменена на: {value}. История чата перезагружена.")
        elif key == "MAX_CHAT_HISTORY_DISPLAY":
            self.view.load_chat_history()
            logger.info(f"Настройка 'Макс. сообщений в истории' изменена на: {value}. История чата перезагружена.")
        elif key == "HIDE_CHAT_TAGS":
            self.view.load_chat_history()
            logger.info(f"Настройка 'Скрывать теги' изменена на: {value}. История чата перезагружена.")


        elif key == "SHOW_TOKEN_INFO":
            self.view.update_token_count()
        elif key == "TOKEN_COST_INPUT":
            self.model.token_cost_input = float(value)
            self.view.update_token_count()
        elif key == "TOKEN_COST_OUTPUT":
            self.model.token_cost_output = float(value)
            self.view.update_token_count()
        elif key == "MAX_MODEL_TOKENS":
            self.model.max_model_tokens = int(value)
            self.view.update_token_count()

    def start_camera_capture_thread(self):
        if not hasattr(self, 'camera_capture') or self.camera_capture is None:
            from camera_capture import CameraCapture
            self.camera_capture = CameraCapture()

        if not self.camera_capture.is_running():
            camera_index = int(self.settings.get("CAMERA_INDEX", 0))
            interval = float(self.settings.get("CAMERA_CAPTURE_INTERVAL", 5.0))
            quality = int(self.settings.get("CAMERA_CAPTURE_QUALITY", 25))
            fps = int(self.settings.get("CAMERA_CAPTURE_FPS", 1))
            max_history_frames = int(self.settings.get("CAMERA_CAPTURE_HISTORY_LIMIT", 3))
            max_frames_per_request = int(self.settings.get("CAMERA_CAPTURE_TRANSFER_LIMIT", 1))
            capture_width = int(self.settings.get("CAMERA_CAPTURE_WIDTH", 640))
            capture_height = int(self.settings.get("CAMERA_CAPTURE_HEIGHT", 480))
            self.camera_capture.start_capture(camera_index, quality, fps, max_history_frames,
                                              max_frames_per_request, capture_width,
                                              capture_height)
            logger.info(f"Поток захвата с камеры запущен с индексом {camera_index}")
            self.camera_capture_active = True
            self.update_status_colors()

    def stop_camera_capture_thread(self):
        if hasattr(self, 'camera_capture') and self.camera_capture is not None and self.camera_capture.is_running():
            self.camera_capture.stop_capture()
            logger.info("Поток захвата с камеры остановлен.")
        self.camera_capture_active = False
        self.update_status_colors()

    def start_screen_capture_thread(self):
        if not self.screen_capture_running:
            interval = float(self.settings.get("SCREEN_CAPTURE_INTERVAL", 5.0))
            quality = int(self.settings.get("SCREEN_CAPTURE_QUALITY", 25))
            fps = int(self.settings.get("SCREEN_CAPTURE_FPS", 1))
            max_history_frames = int(self.settings.get("SCREEN_CAPTURE_HISTORY_LIMIT", 3))
            max_frames_per_request = int(self.settings.get("SCREEN_CAPTURE_TRANSFER_LIMIT", 1))
            capture_width = int(self.settings.get("SCREEN_CAPTURE_WIDTH", 1024))
            capture_height = int(self.settings.get("SCREEN_CAPTURE_HEIGHT", 768))
            self.screen_capture_instance.start_capture(interval, quality, fps, max_history_frames,
                                                       max_frames_per_request, capture_width,
                                                       capture_height)
            self.screen_capture_running = True
            logger.info(f"Поток захвата экрана запущен")
            
            self.screen_capture_active = True
            if self.settings.get("SEND_IMAGE_REQUESTS", 1):
                self.start_image_request_timer()
            self.update_status_colors()

    def stop_screen_capture_thread(self):
        if self.screen_capture_running:
            self.screen_capture_instance.stop_capture()
            self.screen_capture_running = False
            logger.info("Поток захвата экрана остановлен.")
        self.screen_capture_active = False
        self.update_status_colors()

    def start_image_request_timer(self):
        if not self.image_request_timer_running:
            self.image_request_timer_running = True
            self.last_image_request_time = time.time()
            logger.info("Таймер периодической отправки изображений запущен.")

    def stop_image_request_timer(self):
        if self.image_request_timer_running:
            self.image_request_timer_running = False
            logger.info("Таймер периодической отправки изображений остановлен.")

    async def async_send_message(
        self,
        user_input: str,
        system_input: str = "",
        image_data: list[bytes] | None = None
    ):
        try:
            # ПОКАЗЫВАЕМ СТАТУС СРАЗУ В НАЧАЛЕ!
            print("[DEBUG] Начинаем async_send_message, показываем статус")
            self.show_mita_thinking()
            
            is_streaming = bool(self.settings.get("ENABLE_STREAMING", False))

            def stream_callback_handler(chunk: str):
                self.view.append_stream_chunk_signal.emit(chunk)

            if is_streaming:
                self.view.prepare_stream_signal.emit()

            response = await asyncio.wait_for(
                self.loop.run_in_executor(
                    None,
                    lambda: self.model.generate_response(
                        user_input=user_input,
                        system_input=system_input,
                        image_data=image_data,
                        stream_callback=stream_callback_handler if is_streaming else None
                    )
                ),
                timeout=120.0
            )

            # Скрываем статус после успешного ответа
            if response is not None:
                print("[DEBUG] Получили ответ, скрываем статус")
                self.hide_mita_status()

            if is_streaming:
                self.view.finish_stream_signal.emit()
            else:
                self.view.update_chat_signal.emit("assistant", response if response is not None else "...", False, "")

            self.view.update_status_signal.emit()
            self.view.update_debug_signal.emit()
            QTimer.singleShot(0, self.view.update_token_count)

            if self.server and self.server.client_socket:
                final_response_text = response if response else "..."
                try:
                    self.server.send_message_to_server(final_response_text)
                    logger.info("Ответ отправлен в игру.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ в игру: {e}")
                    
        except asyncio.TimeoutError:
            logger.warning("Тайм-аут: генерация ответа заняла слишком много времени.")
            self.show_mita_error("Превышено время ожидания ответа")
        except Exception as e:
            logger.error(f"Ошибка в async_send_message: {e}", exc_info=True)
            self.show_mita_error(f"Ошибка: {str(e)[:50]}...")

    @staticmethod
    def delete_all_sound_files():
        for pattern in ["*.wav", "*.mp3"]:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    logger.info(f"Удален файл: {file}")
                except Exception as e:
                    logger.info(f"Ошибка при удалении файла {file}: {e}")

    async def run_local_voiceover(self, text):
        result_path = None
        try:
            character = self.model.current_character if hasattr(self.model, "current_character") else None
            output_file = f"MitaVoices/output_{uuid.uuid4()}.wav"
            absolute_audio_path = os.path.abspath(output_file)
            os.makedirs(os.path.dirname(absolute_audio_path), exist_ok=True)

            result_path = await self.local_voice.voiceover(
                text=text,
                output_file=absolute_audio_path,
                character=character
            )

            if result_path:
                logger.info(f"Локальная озвучка сохранена в: {result_path}")
                if not self.ConnectedToGame and self.settings.get("VOICEOVER_LOCAL_CHAT"):
                    await AudioHandler.handle_voice_file(result_path, self.settings.get("LOCAL_VOICE_DELETE_AUDIO",
                                                                                        True) if os.environ.get(
                        "ENABLE_VOICE_DELETE_CHECKBOX", "0") == "1" else True)
                elif self.ConnectedToGame:
                    self.patch_to_sound_file = result_path
                    logger.info(f"Путь к файлу для игры: {self.patch_to_sound_file}")
                else:
                    logger.info("Озвучка в локальном чате отключена.")
            else:
                logger.error("Локальная озвучка не удалась, файл не создан.")

        except Exception as e:
            logger.error(f"Ошибка при выполнении локальной озвучки: {e}")

    def init_model_thread(self, model_id, loading_window, status_label, progress):
        try:
            QTimer.singleShot(0, lambda: status_label.setText(_("Загрузка настроек...", "Loading settings...")))

            success = False
            if not self.model_loading_cancelled:
                QTimer.singleShot(0, lambda: status_label.setText(_("Инициализация модели...", "Initializing model...")))
                success = self.local_voice.initialize_model(model_id, init=True)

            if success and not self.model_loading_cancelled:
                QTimer.singleShot(0, functools.partial(self.view.finish_model_loading, model_id, loading_window))
            elif not self.model_loading_cancelled:
                error_message = _("Не удалось инициализировать модель. Проверьте логи.",
                                  "Failed to initialize model. Check logs.")
                QTimer.singleShot(0, lambda: [
                    status_label.setText(_("Ошибка инициализации!", "Initialization Error!")),
                    progress.setRange(0, 1),
                    QMessageBox.critical(loading_window, _("Ошибка инициализации", "Initialization Error"), error_message),
                    self.view.cancel_model_loading(loading_window)
                ])
        except Exception as e:
            logger.error(f"Критическая ошибка в потоке инициализации модели {model_id}: {e}", exc_info=True)
            if not self.model_loading_cancelled:
                error_message = _("Критическая ошибка при инициализации модели: ",
                                  "Critical error during model initialization: ") + str(e)
                QTimer.singleShot(0, lambda: [
                    status_label.setText(_("Ошибка!", "Error!")),
                    progress.setRange(0, 1),
                    QMessageBox.critical(loading_window, _("Ошибка", "Error"), error_message),
                    self.view.cancel_model_loading(loading_window)
                ])

    def refresh_local_voice_modules(self):
        import importlib
        import sys
        logger.info("Попытка обновления модулей локальной озвучки...")

        modules_to_check = {
            "tts_with_rvc": "TTS_RVC",
            "fish_speech_lib.inference": "FishSpeech",
            "f5_tts": None,
            "triton": None
        }
        
        lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Lib")
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)

        for module_name, class_name in modules_to_check.items():
            try:
                if module_name in sys.modules:
                    logger.debug(f"Перезагрузка модуля: {module_name}")
                    importlib.reload(sys.modules[module_name])
                else:
                    logger.debug(f"Импорт модуля: {module_name}")
                    imported_module = importlib.import_module(module_name)

                if class_name:
                    actual_class = getattr(sys.modules[module_name], class_name)
                    if module_name == "tts_with_rvc":
                        self.local_voice.tts_rvc_module = actual_class
                    elif module_name == "fish_speech_lib.inference":
                        self.local_voice.fish_speech_module = actual_class

                logger.info(f"Модуль {module_name} успешно обработан.")
            except ImportError:
                logger.warning(f"Модуль {module_name} не найден или не установлен.")
                if module_name == "tts_with_rvc":
                    self.local_voice.tts_rvc_module = None
                elif module_name == "fish_speech_lib.inference":
                    self.local_voice.fish_speech_module = None
            except Exception as e:
                logger.error(f"Ошибка при обработке модуля {module_name}: {e}", exc_info=True)

        self.view.check_triton_dependencies()

    def check_module_installed(self, module_name):
        logger.info(f"Проверка установки модуля: {module_name}")
        spec = None
        try:
            spec = importlib.util.find_spec(module_name)

            if spec is None:
                logger.info(f"Модуль {module_name} НЕ найден через find_spec.")
                return False
            else:
                if spec.loader is not None:
                    try:
                        module = importlib.import_module(module_name)
                        if hasattr(module, '__spec__') and module.__spec__ is not None:
                            logger.info(f"Модуль {module_name} найден (find_spec + loader + import).")
                            return True
                        else:
                            logger.warning(f"Модуль {module_name} импортирован, но __spec__ is None или отсутствует. Считаем не установленным корректно.")
                            if module_name in sys.modules:
                                try:
                                    del sys.modules[module_name]
                                except KeyError:
                                    pass
                            return False
                    except ImportError as ie:
                        logger.warning(f"Модуль {module_name} найден find_spec, но не импортируется: {ie}. Считаем не установленным.")
                        return False
                    except ValueError as ve:
                        logger.warning(f"Модуль {module_name} найден find_spec, но ошибка ValueError при импорте: {ve}. Считаем не установленным.")
                        return False
                    except Exception as e_import:
                        logger.error(f"Неожиданная ошибка при импорте {module_name} после find_spec: {e_import}")
                        return False
                else:
                    logger.warning(f"Модуль {module_name} найден через find_spec, но loader is None. Считаем не установленным корректно.")
                    return False

        except ValueError as e:
            logger.warning(f"Ошибка ValueError при find_spec для {module_name}: {e}. Считаем не установленным корректно.")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при вызове find_spec для {module_name}: {e}")
            return False

    def check_available_vram(self):
        logger.warning("Проверка VRAM не реализована, возвращается фиктивное значение.")
        try:
            return 100
        except Exception as e:
            logger.error(f"Ошибка при попытке проверки VRAM: {e}")
            return 4

    def _ffmpeg_install_thread_target(self):
        QTimer.singleShot(0, self.view._show_ffmpeg_installing_popup)

        logger.info("Starting FFmpeg installation attempt...")
        success = install_ffmpeg()
        logger.info(f"FFmpeg installation attempt finished. Success: {success}")

        QTimer.singleShot(0, self.view._close_ffmpeg_installing_popup)

        if not success:
            QTimer.singleShot(0, self.view._show_ffmpeg_error_popup)

    def check_and_install_ffmpeg(self):
        ffmpeg_path = Path(".") / "ffmpeg.exe"
        logger.info(f"Checking for FFmpeg at: {ffmpeg_path}")

        if not ffmpeg_path.exists():
            logger.info("FFmpeg not found. Starting installation process in a separate thread.")
            install_thread = threading.Thread(target=self._ffmpeg_install_thread_target, daemon=True)
            install_thread.start()
        else:
            logger.info("FFmpeg found. No installation needed.")

    def close_app(self):
        self.stop_screen_capture_thread()
        self.stop_camera_capture_thread()
        self.delete_all_sound_files()
        self.stop_server()
        logger.info("Закрываемся")

    @property
    def update_debug_signal(self):
        """Делегирует доступ к сигналу обновления отладки"""
        if self.view:
            return self.view.update_debug_signal
        return None

    @property
    def update_chat_signal(self):
        """Делегирует доступ к сигналу обновления чата"""
        if self.view:
            return self.view.update_chat_signal
        return None

    @property
    def update_status_signal(self):
        """Делегирует доступ к сигналу обновления статуса"""
        if self.view:
            return self.view.update_status_signal
        return None

    @property
    def prepare_stream_signal(self):
        """Делегирует доступ к сигналу подготовки стрима"""
        if self.view:
            return self.view.prepare_stream_signal
        return None

    @property
    def append_stream_chunk_signal(self):
        """Делегирует доступ к сигналу добавления куска стрима"""
        if self.view:
            return self.view.append_stream_chunk_signal
        return None

    @property
    def finish_stream_signal(self):
        """Делегирует доступ к сигналу завершения стрима"""
        if self.view:
            return self.view.finish_stream_signal
        return None
    
    def show_mita_thinking(self):
        """Показать, что Мита думает (через сигнал)"""
        print("[DEBUG] Controller: запрос на показ статуса 'думает'")
        if self.view and hasattr(self.view, 'show_thinking_signal'):
            character_name = self.model.current_character.name if self.model.current_character else "Мита"
            self.view.show_thinking_signal.emit(character_name)
        else:
            print("[DEBUG] view или show_thinking_signal не найден!")
            
    def show_mita_error(self, error_message):
        """Показать ошибку Миты (через сигнал)"""
        print(f"[DEBUG] Controller: запрос на показ ошибки: {error_message}")
        if self.view and hasattr(self.view, 'show_error_signal'):
            self.view.show_error_signal.emit(error_message)
            
    def hide_mita_status(self):
        """Скрыть статус Миты (через сигнал)"""
        print("[DEBUG] Controller: запрос на скрытие статуса")
        if self.view and hasattr(self.view, 'hide_status_signal'):
            self.view.hide_status_signal.emit()
        else:
            print("[DEBUG] view или hide_status_signal не найден при попытке скрыть!")

    def show_mita_error_pulse(self):
        """Послать сигнал для 'пульсации' статуса красным."""
        if self.view and hasattr(self.view, 'pulse_error_signal'):
            self.view.pulse_error_signal.emit()

    def update_status_colors(self):
        if self.view:
            self.view.update_status_colors()