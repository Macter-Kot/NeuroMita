import os
import base64
import json
from typing import Dict, Any

from managers.settings_manager import SettingsManager
from main_logger import logger
from utils import SH
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer

class SettingsController:
    def __init__(self, main_controller, config_path):
        self.main = main_controller
        self.config_path = config_path
        self.settings = SettingsManager(self.config_path)
        
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

            self.main.api_key = settings.get("NM_API_KEY", "")
            self.main.api_key_res = settings.get("NM_API_KEY_RES", "")
            self.main.api_url = settings.get("NM_API_URL", "")
            self.main.api_model = settings.get("NM_API_MODEL", "")
            self.main.makeRequest = settings.get("NM_API_REQ", False)

            self.main.telegram_controller.api_id = settings.get("NM_TELEGRAM_API_ID", "")
            self.main.telegram_controller.api_hash = settings.get("NM_TELEGRAM_API_HASH", "")
            self.main.telegram_controller.phone = settings.get("NM_TELEGRAM_PHONE", "")

            logger.info(f"Итого загружено {SH(self.main.api_key)},{SH(self.main.api_key_res)},{self.main.api_url},{self.main.api_model},{self.main.makeRequest} (Должно быть не пусто)")
            logger.info(f"По тг {SH(self.main.telegram_controller.api_id)},{SH(self.main.telegram_controller.api_hash)},{SH(self.main.telegram_controller.phone)} (Должно быть не пусто если тг)")
            
            if update_model:
                if self.main.api_key:
                    self.main.model_controller.model.api_key = self.main.api_key
                if self.main.api_url:
                    self.main.model_controller.model.api_url = self.main.api_url
                if self.main.api_model:
                    self.main.model_controller.model.api_model = self.main.api_model
                self.main.model_controller.model.makeRequest = self.main.makeRequest
                self.main.model_controller.model.update_openai_client()

            logger.info("Настройки загружены из файла")
        except Exception as e:
            logger.info(f"Ошибка загрузки: {e}")
            
    def all_settings_actions(self, key, value):
        if key in ["SILERO_USE", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            self.main.view.switch_voiceover_settings()

        if key == "SILERO_TIME":
            self.main.telegram_controller.bot_handler.silero_time_limit = int(value)

        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                QMessageBox.information(self.main.view, "Информация",
                    "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)")

            if self.main.telegram_controller.bot_handler:
                self.main.telegram_controller.bot_handler.tg_bot = value
                
        elif key in ["CHARACTER", "NM_API_MODEL", "NM_API_KEY", "NM_API_URL", "NM_API_REQ", "gpt4free_model",
                     "MODEL_MAX_RESPONSE_TOKENS", "MODEL_TEMPERATURE", "MODEL_PRESENCE_PENALTY",
                     "MODEL_FREQUENCY_PENALTY", "MODEL_LOG_PROBABILITY", "MODEL_TOP_K", "MODEL_TOP_P",
                     "MODEL_THOUGHT_PROCESS", "MODEL_MESSAGE_LIMIT", "MODEL_MESSAGE_ATTEMPTS_COUNT",
                     "MODEL_MESSAGE_ATTEMPTS_TIME", "IMAGE_QUALITY_REDUCTION_ENABLED",
                     "IMAGE_QUALITY_REDUCTION_START_INDEX", "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE",
                     "IMAGE_QUALITY_REDUCTION_MIN_QUALITY", "IMAGE_QUALITY_REDUCTION_DECREASE_RATE",
                     "ENABLE_HISTORY_COMPRESSION_ON_LIMIT", "ENABLE_HISTORY_COMPRESSION_PERIODIC",
                     "HISTORY_COMPRESSION_OUTPUT_TARGET", "HISTORY_COMPRESSION_PERIODIC_INTERVAL",
                     "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS"]:
            self.main.model_controller.update_model_settings(key, value)
            
        elif key in ["MIC_ACTIVE", "RECOGNIZER_TYPE", "VOSK_MODEL", "SILENCE_THRESHOLD",
                     "SILENCE_DURATION", "VOSK_PROCESS_INTERVAL"]:
            self.main.speech_controller.update_speech_settings(key, value)
            
        elif key == "ENABLE_SCREEN_ANALYSIS":
            if bool(value):
                self.main.capture_controller.start_screen_capture_thread()
            else:
                self.main.capture_controller.stop_screen_capture_thread()
        elif key == "ENABLE_CAMERA_CAPTURE":
            if bool(value):
                self.main.capture_controller.start_camera_capture_thread()
            else:
                self.main.capture_controller.stop_camera_capture_thread()
        elif key in ["SCREEN_CAPTURE_INTERVAL", "SCREEN_CAPTURE_QUALITY", "SCREEN_CAPTURE_FPS",
                     "SCREEN_CAPTURE_HISTORY_LIMIT", "SCREEN_CAPTURE_TRANSFER_LIMIT", "SCREEN_CAPTURE_WIDTH",
                     "SCREEN_CAPTURE_HEIGHT"]:
            if self.main.capture_controller.screen_capture_instance and self.main.capture_controller.screen_capture_instance.is_running():
                logger.info(f"Настройка захвата экрана '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.main.capture_controller.stop_screen_capture_thread()
                self.main.capture_controller.start_screen_capture_thread()
            else:
                logger.info(
                    f"Настройка захвата экрана '{key}' изменена на '{value}'.")
        elif key == "SEND_IMAGE_REQUESTS":
            if bool(value):
                self.main.capture_controller.start_image_request_timer()
            else:
                self.main.capture_controller.stop_image_request_timer()
        elif key == "IMAGE_REQUEST_INTERVAL":
            if self.main.capture_controller.image_request_timer_running:
                logger.info(f"Настройка интервала запросов изображений изменена на '{value}'. ")
                self.main.capture_controller.stop_image_request_timer()
                self.main.capture_controller.start_image_request_timer()
            else:
                logger.info(
                    f"Настройка интервала запросов изображений изменена на '{value}'. Таймер не активен, изменения будут применены при следующем запуске.")
        elif key in ["EXCLUDE_GUI_WINDOW", "EXCLUDE_WINDOW_TITLE"]:
            from win32 import win32gui
            exclude_gui = self.settings.get("EXCLUDE_GUI_WINDOW", False)
            exclude_title = self.settings.get("EXCLUDE_WINDOW_TITLE", "")

            hwnd_to_pass = None
            if exclude_gui:
                hwnd_to_pass = self.main.view.root.winfo_id()
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

            if self.main.capture_controller.screen_capture_instance:
                self.main.capture_controller.screen_capture_instance.set_exclusion_parameters(hwnd_to_pass, exclude_title,
                                                                      exclude_gui or bool(exclude_title))
                logger.info(
                    f"Параметры исключения окна переданы в ScreenCapture: exclude_gui={exclude_gui}, exclude_title='{exclude_title}'")

            if self.main.capture_controller.screen_capture_instance and self.main.capture_controller.screen_capture_instance.is_running():
                logger.info(f"Настройка исключения окна '{key}' изменена на '{value}'.")
                self.main.capture_controller.stop_screen_capture_thread()
                self.main.capture_controller.start_screen_capture_thread()
            else:
                logger.info(
                    f"Настройка исключения окна '{key}' изменена на '{value}'.")
                    
        if key == "CHAT_FONT_SIZE":
            try:
                font_size = int(value)
                self.main.view.update_chat_font_size(font_size)
                self.main.view.load_chat_history()
                logger.info(f"Размер шрифта чата изменен на: {font_size}. История перезагружена.")
            except ValueError:
                logger.warning(f"Неверное значение для размера шрифта чата: {value}")
            except Exception as e:
                logger.error(f"Ошибка при изменении размера шрифта чата: {e}")
        elif key == "SHOW_CHAT_TIMESTAMPS":
            self.main.view.load_chat_history()
            logger.info(f"Настройка 'Показывать метки времени' изменена на: {value}. История чата перезагружена.")
        elif key == "MAX_CHAT_HISTORY_DISPLAY":
            self.main.view.load_chat_history()
            logger.info(f"Настройка 'Макс. сообщений в истории' изменена на: {value}. История чата перезагружена.")
        elif key == "HIDE_CHAT_TAGS":
            self.main.view.load_chat_history()
            logger.info(f"Настройка 'Скрывать теги' изменена на: {value}. История чата перезагружена.")

        elif key == "SHOW_TOKEN_INFO":
            self.main.view.update_token_count()
        elif key == "TOKEN_COST_INPUT":
            self.main.model_controller.model.token_cost_input = float(value)
            self.main.view.update_token_count()
        elif key == "TOKEN_COST_OUTPUT":
            self.main.model_controller.model.token_cost_output = float(value)
            self.main.view.update_token_count()
        elif key == "MAX_MODEL_TOKENS":
            self.main.model_controller.model.max_model_tokens = int(value)
            self.main.view.update_token_count()

    @staticmethod
    def get_app_vars() -> Dict[str, Any]:
        """
        Возвращает публичные переменные программы для использования в DSL-скриптах.

        Поддерживаются два способа добавления переменных:
        1. Через список ключей (берётся значение из SettingsManager и преобразуется в bool)
        2. Через кастомный словарь {имя_переменной: значение}

        Возвращаемый словарь можно спокойно расширять.
        """
        # Простые флаги: автоматическое получение из SettingsManager с преобразованием в bool
        bool_keys = [
            "ENABLE_CAMERA_CAPTURE",
            "ENABLE_SCREEN_ANALYSIS",
            "MIC_ACTIVE",
            # Добавь сюда другие ключи, если нужно
        ]

        # Кастомные переменные: имя переменной => конкретное значение
        custom_vars: Dict[str, Any] = {
            "app_version": "1.0.0",
            # "custom_flag": some_function(),
        }

        # Собираем переменные-флаги
        flag_vars: Dict[str, Any] = {
            key: bool(SettingsManager.get(key, False))
            for key in bool_keys
        }

        # Объединяем всё в один словарь, приоритет у custom_vars
        return {**flag_vars, **custom_vars}