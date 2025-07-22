import os
import base64
import json
from typing import Dict, Any

from managers.settings_manager import SettingsManager
from main_logger import logger
from utils import SH
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtCore import QTimer
from core.events import get_event_bus, Events, Event


class SettingsController:
    def __init__(self, config_path):
        self.config_path = config_path
        self.event_bus = get_event_bus()
        self._subscribe_to_events()
        self.settings = SettingsManager(self.config_path)
        

    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Settings.GET_SETTINGS, self._on_get_settings, weak=False)
        self.event_bus.subscribe(Events.Settings.GET_SETTING, self._on_get_setting, weak=False)
        self.event_bus.subscribe(Events.Settings.SAVE_SETTING, self._on_save_setting, weak=False)
        
    def load_api_settings(self, update_model):
        logger.info("Начинаю загрузку настроек (из уже загруженного словаря)")

        settings_dict = self.settings.settings

        if not settings_dict:
            logger.info("Настройки пустые (файл не найден или повреждён), используем дефолты")
            return

        api_key = settings_dict.get("NM_API_KEY", "")
        api_key_res = settings_dict.get("NM_API_KEY_RES", "")
        api_url = settings_dict.get("NM_API_URL", "")
        api_model = settings_dict.get("NM_API_MODEL", "")
        makeRequest = settings_dict.get("NM_API_REQ", False)

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

        logger.info(f"Итого загружено {SH(api_key)},{SH(api_key_res)},{api_url},{api_model},{makeRequest} (Должно быть не пусто)")
        logger.info(f"По тг {SH(telegram_settings['api_id'])},{SH(telegram_settings['api_hash'])},{SH(telegram_settings['phone'])} (Должно быть не пусто если тг)")
        
        if update_model:
            model_settings = {
                'api_key': api_key,
                'api_key_res': api_key_res,
                'api_url': api_url,
                'api_model': api_model,
                'makeRequest': makeRequest
            }
            self.event_bus.emit("model_settings_loaded", model_settings)

        logger.info("Настройки применены из загруженного словаря")

    def _on_get_settings(self, event: Event):
        return self.settings
    
    def _on_save_setting(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key:
            self.settings.set(key, value)
            self.settings.save_settings()
            self.update_setting(key, value)
    
    def _on_get_setting(self, event: Event):
        key = event.data.get('key')
        default = event.data.get('default', None)
        
        return self.settings.get(key, default)
    
    def update_setting(self, key, value):
        self.settings.set(key, value)
        self.settings.save_settings()
        
        self.event_bus.emit(Events.Core.SETTING_CHANGED, {"key": key, "value": value})
        
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