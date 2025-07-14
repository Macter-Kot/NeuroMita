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
        self.settings = SettingsManager(self.config_path)
        
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

        telegram_settings = {
            "api_id": settings_dict.get("NM_TELEGRAM_API_ID", ""),
            "api_hash": settings_dict.get("NM_TELEGRAM_API_HASH", ""),
            "phone": settings_dict.get("NM_TELEGRAM_PHONE", ""),
            "settings": self.settings
        }
        self.event_bus.emit("telegram_settings_loaded", telegram_settings)
        
        capture_settings = {
            "settings": self.settings
        }
        self.event_bus.emit("capture_settings_loaded", capture_settings)
        
        speech_settings = {
            "settings": self.settings
        }
        self.event_bus.emit("speech_settings_loaded", speech_settings)

        logger.info(f"Итого загружено {SH(self.main.api_key)},{SH(self.main.api_key_res)},{self.main.api_url},{self.main.api_model},{self.main.makeRequest} (Должно быть не пусто)")
        logger.info(f"По тг {SH(telegram_settings['api_id'])},{SH(telegram_settings['api_hash'])},{SH(telegram_settings['phone'])} (Должно быть не пусто если тг)")
        
        if update_model:
            model_settings = {
                'api_key': self.main.api_key,
                'api_url': self.main.api_url,
                'api_model': self.main.api_model,
                'makeRequest': self.main.makeRequest
            }
            self.event_bus.emit("model_settings_loaded", model_settings)

        logger.info("Настройки применены из загруженного словаря")

    def all_settings_actions(self, key, value):
        self.settings.set(key, value)
        self.settings.save_settings()
        
        if key in ["SILERO_USE", "VOICEOVER_METHOD", "AUDIO_BOT"]:
            self.event_bus.emit(Events.SWITCH_VOICEOVER_SETTINGS)

        if key in ["SILERO_TIME", "AUDIO_BOT"]:
            self.event_bus.emit("telegram_settings_changed", {"key": key, "value": value})

        if key == "AUDIO_BOT":
            if value.startswith("@CrazyMitaAIbot"):
                self.event_bus.emit(Events.SHOW_INFO_MESSAGE, {
                    "title": "Информация",
                    "message": "VinerX: наши товарищи из CrazyMitaAIbot предоставляет озвучку бесплатно буквально со своих пк, будет время - загляните к ним в тг, скажите спасибо)"
                })

        elif key == "CHARACTER":
            self.event_bus.emit("model_character_change", {"character": value})

        elif key in ["NM_API_MODEL", "NM_API_KEY", "NM_API_URL", "NM_API_REQ", "gpt4free_model",
                    "MODEL_MAX_RESPONSE_TOKENS", "MODEL_TEMPERATURE", "MODEL_PRESENCE_PENALTY",
                    "MODEL_FREQUENCY_PENALTY", "MODEL_LOG_PROBABILITY", "MODEL_TOP_K", "MODEL_TOP_P",
                    "MODEL_THOUGHT_PROCESS", "MODEL_MESSAGE_LIMIT", "MODEL_MESSAGE_ATTEMPTS_COUNT",
                    "MODEL_MESSAGE_ATTEMPTS_TIME", "IMAGE_QUALITY_REDUCTION_ENABLED",
                    "IMAGE_QUALITY_REDUCTION_START_INDEX", "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE",
                    "IMAGE_QUALITY_REDUCTION_MIN_QUALITY", "IMAGE_QUALITY_REDUCTION_DECREASE_RATE",
                    "ENABLE_HISTORY_COMPRESSION_ON_LIMIT", "ENABLE_HISTORY_COMPRESSION_PERIODIC",
                    "HISTORY_COMPRESSION_OUTPUT_TARGET", "HISTORY_COMPRESSION_PERIODIC_INTERVAL",
                    "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS", "TOKEN_COST_INPUT", "TOKEN_COST_OUTPUT",
                    "MAX_MODEL_TOKENS"]:
            self.event_bus.emit("model_setting_changed", {"key": key, "value": value})

        elif key in ["MIC_ACTIVE", "RECOGNIZER_TYPE", "VOSK_MODEL", "SILENCE_THRESHOLD", "SILENCE_DURATION", "VOSK_PROCESS_INTERVAL"]:
            self.event_bus.emit("speech_setting_changed", {"key": key, "value": value})

        elif key == "ENABLE_SCREEN_ANALYSIS":
            if bool(value):
                self.event_bus.emit("start_screen_capture")
            else:
                self.event_bus.emit("stop_screen_capture")
        elif key in ["SCREEN_CAPTURE_INTERVAL", "SCREEN_CAPTURE_QUALITY", "SCREEN_CAPTURE_FPS",
                    "SCREEN_CAPTURE_HISTORY_LIMIT", "SCREEN_CAPTURE_TRANSFER_LIMIT", 
                    "SCREEN_CAPTURE_WIDTH", "SCREEN_CAPTURE_HEIGHT"]:
            logger.info(f"Настройка захвата экрана '{key}' изменена на '{value}'. Перезапускаю поток захвата.")
            self.event_bus.emit("stop_screen_capture")
            self.event_bus.emit("start_screen_capture")

        elif key == "ENABLE_CAMERA_CAPTURE":
            if bool(value):
                self.event_bus.emit("start_camera_capture")
            else:
                self.event_bus.emit("stop_camera_capture")

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

            self.event_bus.emit("update_screen_capture_exclusion", {
                'hwnd': hwnd_to_pass,
                'exclude_title': exclude_title,
                'exclude_enabled': exclude_gui or bool(exclude_title)
            })

        elif key == "SEND_IMAGE_REQUESTS":
            if bool(value):
                self.event_bus.emit("start_image_request_timer")
            else:
                self.event_bus.emit("stop_image_request_timer")
        elif key == "IMAGE_REQUEST_INTERVAL":
            self.event_bus.emit("stop_image_request_timer")
            self.event_bus.emit("start_image_request_timer")

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

        elif key == "SHOW_TOKEN_INFO":
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)

        if key in ["MIC_ACTIVE", "ENABLE_SCREEN_ANALYSIS", "ENABLE_CAMERA_CAPTURE"]:
            self.event_bus.emit(Events.UPDATE_STATUS_COLORS)

        logger.debug(f"Настройка '{key}' успешно применена со значением: {value}")

    @staticmethod
    def get_app_vars() -> Dict[str, Any]:
        bool_keys = [
            "ENABLE_CAMERA_CAPTURE",
            "ENABLE_SCREEN_ANALYSIS",
            "MIC_ACTIVE",
        ]

        custom_vars: Dict[str, Any] = {
            "app_version": "1.0.0",
        }

        flag_vars: Dict[str, Any] = {
            key: bool(SettingsManager.get(key, False))
            for key in bool_keys
        }

        return {**flag_vars, **custom_vars}