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
        
        self.event_bus.emit("setting_changed", {"key": key, "value": value})
        
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