import os
import base64
import json
from typing import Dict, Any

from managers.settings_manager import SettingsManager
from main_logger import logger
from utils import SH
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer
from core.events import get_event_bus, Events

class SettingsController:
    def __init__(self, main_controller, config_path):
        self.main = main_controller
        self.config_path = config_path
        self.event_bus = get_event_bus()
        self.settings = SettingsManager(self.config_path)  # Создаем свой экземпляр SettingsManager
        
    def load_api_settings(self, update_model):
        logger.info("Начинаю загрузку настроек (из уже загруженного словаря)")

        settings_dict = self.settings.settings

        if not settings_dict:
            logger.info("Настройки пустые (файл не найден или повреждён), используем дефолты")
            return

        self.main.api_key = settings_dict.get("NM_API_KEY", "")
        self.main.api_key_res = settings_dict.get("NM_API_KEY_RES", "")
        self.main.api_url = settings_dict.get("NM_API_URL", "")
        self.main.api_model = settings_dict.get("NM_API_MODEL", "")
        self.main.makeRequest = settings_dict.get("NM_API_REQ", False)

        self.main.telegram_controller.api_id = settings_dict.get("NM_TELEGRAM_API_ID", "")
        self.main.telegram_controller.api_hash = settings_dict.get("NM_TELEGRAM_API_HASH", "")
        self.main.telegram_controller.phone = settings_dict.get("NM_TELEGRAM_PHONE", "")

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

        logger.info("Настройки применены из загруженного словаря")

    def all_settings_actions(self, key, value):
        """
        Обновленная функция обработки изменений настроек с учетом новой архитектуры контроллеров
        """
        # Сохраняем настройку
        self.settings.set(key, value)
        self.settings.save_settings()
        
        # Аудио и озвучка
        if key in ["SILERO_USE", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            self.event_bus.emit(Events.SWITCH_VOICEOVER_SETTINGS)

        if key == "SILERO_TIME":
            if self.main.telegram_controller.bot_handler:
                self.main.telegram_controller.bot_handler.silero_time_limit = int(value)

        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                self.event_bus.emit(Events.SHOW_INFO_MESSAGE, {
                    "title": "Информация",
                    "message": "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)"
                })

            if self.main.telegram_controller.bot_handler:
                self.main.telegram_controller.bot_handler.tg_bot = value

        # Персонажи
        elif key == "CHARACTER":
            self.main.model_controller.model.current_character_to_change = value
            self.main.model_controller.model.check_change_current_character()

        # API настройки модели
        elif key == "NM_API_MODEL":
            self.main.model_controller.model.api_model = value.strip()
        elif key == "NM_API_KEY":
            self.main.model_controller.model.api_key = value.strip()
        elif key == "NM_API_URL":
            self.main.model_controller.model.api_url = value.strip()
        elif key == "NM_API_REQ":
            self.main.model_controller.model.makeRequest = bool(value)
        elif key == "gpt4free_model":
            self.main.model_controller.model.gpt4free_model = value.strip()

        # Параметры модели
        elif key == "MODEL_MAX_RESPONSE_TOKENS":
            self.main.model_controller.model.max_response_tokens = int(value)
        elif key == "MODEL_TEMPERATURE":
            self.main.model_controller.model.temperature = float(value)
        elif key == "MODEL_PRESENCE_PENALTY":
            self.main.model_controller.model.presence_penalty = float(value)
        elif key == "MODEL_FREQUENCY_PENALTY":
            self.main.model_controller.model.frequency_penalty = float(value)
        elif key == "MODEL_LOG_PROBABILITY":
            self.main.model_controller.model.log_probability = float(value)
        elif key == "MODEL_TOP_K":
            self.main.model_controller.model.top_k = int(value)
        elif key == "MODEL_TOP_P":
            self.main.model_controller.model.top_p = float(value)
        elif key == "MODEL_THOUGHT_PROCESS":
            self.main.model_controller.model.thinking_budget = float(value)

        # Память и попытки
        elif key == "MODEL_MESSAGE_LIMIT":
            self.main.model_controller.model.memory_limit = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_COUNT":
            self.main.model_controller.model.max_request_attempts = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_TIME":
            self.main.model_controller.model.request_delay = float(value)

        # Микрофон и распознавание речи
        elif key == "MIC_ACTIVE":
            self.main.speech_controller.update_speech_settings(key, value)
        elif key in ["RECOGNIZER_TYPE", "VOSK_MODEL", "SILENCE_THRESHOLD", "SILENCE_DURATION", "VOSK_PROCESS_INTERVAL"]:
            self.main.speech_controller.update_speech_settings(key, value)

        # Захват экрана
        elif key == "ENABLE_SCREEN_ANALYSIS":
            if bool(value):
                self.main.capture_controller.start_screen_capture_thread()
            else:
                self.main.capture_controller.stop_screen_capture_thread()
        elif key in ["SCREEN_CAPTURE_INTERVAL", "SCREEN_CAPTURE_QUALITY", "SCREEN_CAPTURE_FPS",
                    "SCREEN_CAPTURE_HISTORY_LIMIT", "SCREEN_CAPTURE_TRANSFER_LIMIT", 
                    "SCREEN_CAPTURE_WIDTH", "SCREEN_CAPTURE_HEIGHT"]:
            if (hasattr(self.main.capture_controller, 'screen_capture_instance') and 
                self.main.capture_controller.screen_capture_instance and 
                self.main.capture_controller.screen_capture_instance.is_running()):
                logger.info(f"Настройка захвата экрана '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
                self.main.capture_controller.stop_screen_capture_thread()
                self.main.capture_controller.start_screen_capture_thread()

        # Захват камеры
        elif key == "ENABLE_CAMERA_CAPTURE":
            if bool(value):
                self.main.capture_controller.start_camera_capture_thread()
            else:
                self.main.capture_controller.stop_camera_capture_thread()

        # Исключения окон при захвате
        elif key in ["EXCLUDE_GUI_WINDOW", "EXCLUDE_WINDOW_TITLE"]:
            exclude_gui = self.settings.get("EXCLUDE_GUI_WINDOW", False)
            exclude_title = self.settings.get("EXCLUDE_WINDOW_TITLE", "")

            hwnd_to_pass = None
            if exclude_gui:
                hwnd_to_pass = self.event_bus.emit_and_wait(Events.GET_GUI_WINDOW_ID, timeout=0.5)
                hwnd_to_pass = hwnd_to_pass[0] if hwnd_to_pass else None
                logger.info(f"Получен HWND окна GUI для исключения: {hwnd_to_pass}")
            elif exclude_title:
                try:
                    from win32 import win32gui
                    hwnd_to_pass = win32gui.FindWindow(None, exclude_title)
                    if hwnd_to_pass:
                        logger.info(f"Найден HWND для заголовка '{exclude_title}': {hwnd_to_pass}")
                    else:
                        logger.warning(f"Окно с заголовком '{exclude_title}' не найдено.")
                except Exception as e:
                    logger.error(f"Ошибка при поиске окна по заголовку '{exclude_title}': {e}")

            if hasattr(self.main.capture_controller, 'screen_capture_instance') and self.main.capture_controller.screen_capture_instance:
                self.main.capture_controller.screen_capture_instance.set_exclusion_parameters(
                    hwnd_to_pass, exclude_title, exclude_gui or bool(exclude_title))
                
                if self.main.capture_controller.screen_capture_instance.is_running():
                    self.main.capture_controller.stop_screen_capture_thread()
                    self.main.capture_controller.start_screen_capture_thread()

        # Периодические запросы изображений
        elif key == "SEND_IMAGE_REQUESTS":
            if bool(value):
                self.main.capture_controller.start_image_request_timer()
            else:
                self.main.capture_controller.stop_image_request_timer()
        elif key == "IMAGE_REQUEST_INTERVAL":
            if self.main.capture_controller.image_request_timer_running:
                self.main.capture_controller.stop_image_request_timer()
                self.main.capture_controller.start_image_request_timer()

        # Сжатие изображений
        elif key == "IMAGE_QUALITY_REDUCTION_ENABLED":
            self.main.model_controller.model.image_quality_reduction_enabled = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_START_INDEX":
            self.main.model_controller.model.image_quality_reduction_start_index = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE":
            self.main.model_controller.model.image_quality_reduction_use_percentage = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_MIN_QUALITY":
            self.main.model_controller.model.image_quality_reduction_min_quality = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_DECREASE_RATE":
            self.main.model_controller.model.image_quality_reduction_decrease_rate = int(value)

        # Сжатие истории
        elif key == "ENABLE_HISTORY_COMPRESSION_ON_LIMIT":
            self.main.model_controller.model.enable_history_compression_on_limit = bool(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_PERIODIC":
            self.main.model_controller.model.enable_history_compression_periodic = bool(value)
        elif key == "HISTORY_COMPRESSION_OUTPUT_TARGET":
            self.main.model_controller.model.history_compression_output_target = str(value)
        elif key == "HISTORY_COMPRESSION_PERIODIC_INTERVAL":
            self.main.model_controller.model.history_compression_periodic_interval = int(value)
        elif key == "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS":
            self.main.model_controller.model.history_compression_min_messages_to_compress = float(value)

        # Настройки интерфейса
        elif key == "CHAT_FONT_SIZE":
            try:
                font_size = int(value)
                self.event_bus.emit(Events.UPDATE_CHAT_FONT_SIZE, {"font_size": font_size})
                self.event_bus.emit(Events.RELOAD_CHAT_HISTORY)
                logger.info(f"Размер шрифта чата изменен на: {font_size}")
            except ValueError:
                logger.warning(f"Неверное значение для размера шрифта: {value}")
            except Exception as e:
                logger.error(f"Ошибка при изменении размера шрифта: {e}")
                
        elif key in ["SHOW_CHAT_TIMESTAMPS", "MAX_CHAT_HISTORY_DISPLAY", "HIDE_CHAT_TAGS"]:
            self.event_bus.emit(Events.RELOAD_CHAT_HISTORY)
            logger.info(f"Настройка '{key}' изменена на: {value}. История чата перезагружена.")

        # Информация о токенах
        elif key == "SHOW_TOKEN_INFO":
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)
        elif key in ["TOKEN_COST_INPUT", "TOKEN_COST_OUTPUT"]:
            if key == "TOKEN_COST_INPUT":
                self.main.model_controller.model.token_cost_input = float(value)
            else:
                self.main.model_controller.model.token_cost_output = float(value)
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)
        elif key == "MAX_MODEL_TOKENS":
            self.main.model_controller.model.max_model_tokens = int(value)
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)

        # Обновляем цвета статуса если нужно
        if key in ["MIC_ACTIVE", "ENABLE_SCREEN_ANALYSIS", "ENABLE_CAMERA_CAPTURE"]:
            self.event_bus.emit(Events.UPDATE_STATUS_COLORS)

        logger.debug(f"Настройка '{key}' успешно применена со значением: {value}")

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