import os
import asyncio
import threading
import tempfile
import time
from pathlib import Path
from PyQt6.QtCore import QTimer

from controllers.gui_controller import GuiController
from controllers.audio_controller import AudioController
from controllers.telegram_controller import TelegramController
from controllers.capture_controller import CaptureController
from controllers.model_controller import ModelController
from controllers.speech_controller import SpeechController
from controllers.server_controller import ServerController
from controllers.settings_controller import SettingsController
from controllers.chat_controller import ChatController
from controllers.loop_controller import LoopController

from main_logger import logger
from utils.ffmpeg_installer import install_ffmpeg
from utils.pip_installer import PipInstaller
from core.events import get_event_bus, Events, Event


class MainController:
    def __init__(self, view):
        self.view = view
        self.event_bus = get_event_bus()
        

        self.ConnectedToGame = False


        self.api_key = ""
        self.api_key_res = ""
        self.api_url = ""
        self.api_model = ""
        self.makeRequest = False

        self.dialog_active = False

        self.lazy_load_batch_size = 50
        self.total_messages_in_history = 0
        self.loaded_messages_offset = 0
        self.loading_more_history = False

        self.staged_images = []

        self.loop_controller = LoopController(self)
        logger.warning("LoopController успешно инициализирован.")

        self.gui_controller = None

        self.telegram_controller = TelegramController()
        logger.warning("TelegramController успешно инициализирован.")
        

        try:
            target_folder = "Settings"
            os.makedirs(target_folder, exist_ok=True)
            self.config_path = os.path.join(target_folder, "settings.json")

            self.settings_controller = SettingsController(self, self.config_path)
            self.settings = self.settings_controller.settings
        except Exception as e:
            logger.info("Не удалось удачно получить из системных переменных все данные", e)
            self.settings = SettingsController(self, "Settings/settings.json").settings

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

        
        self.audio_controller = AudioController(self)
        logger.warning("AudioController успешно инициализирован.")
        self.model_controller = ModelController(self, self.api_key, self.api_key_res, self.api_url, 
                                               self.api_model, self.makeRequest, self.pip_installer)
        logger.warning("ModelController успешно инициализирован.")
        self.capture_controller = CaptureController(self.settings)
        logger.warning("CaptureController успешно инициализирован.")
        self.speech_controller = SpeechController(self)
        logger.warning("SpeechController успешно инициализирован.")
        self.server_controller = ServerController()
        logger.warning("ServerController успешно инициализирован.")
        self.chat_controller = ChatController(self.settings)
        logger.warning("ChatController успешно инициализирован.")

        

        self.audio_controller.delete_all_sound_files()

        
        self._subscribe_to_events()
        logger.info("MainController подписался на события")
        

    def update_view(self, view):
        if not self.gui_controller:
            self.view = view
            self.gui_controller = GuiController(self, view)
            logger.warning("GuiController успешно инициализирован.")
            self.settings_controller.load_api_settings(False)
            if self.settings.get('VOICEOVER_METHOD') == 'TG' and self.settings.get('USE_VOICEOVER', False):
                self.telegram_controller.start_silero_async()
    
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.CLEAR_CHAT, self._on_clear_chat, weak=False)
        
        self.event_bus.subscribe(Events.SAVE_SETTING, self._on_save_setting, weak=False)
        self.event_bus.subscribe(Events.GET_SETTING, self._on_get_setting, weak=False)
        
        self.event_bus.subscribe(Events.STAGE_IMAGE, self._on_stage_image, weak=False)
        self.event_bus.subscribe(Events.CLEAR_STAGED_IMAGES, self._on_clear_staged_images, weak=False)
        
        self.event_bus.subscribe(Events.GET_CONNECTION_STATUS, self._on_get_connection_status, weak=False)
        
        self.event_bus.subscribe(Events.SCHEDULE_G4F_UPDATE, self._on_schedule_g4f_update, weak=False)
        
        self.event_bus.subscribe(Events.REQUEST_TG_CODE, self._on_request_tg_code, weak=False)
        self.event_bus.subscribe(Events.REQUEST_TG_PASSWORD, self._on_request_tg_password, weak=False)
        
        self.event_bus.subscribe(Events.SET_MICROPHONE, self._on_set_microphone, weak=False)
        self.event_bus.subscribe(Events.START_SPEECH_RECOGNITION, self._on_start_speech_recognition, weak=False)
        self.event_bus.subscribe(Events.STOP_SPEECH_RECOGNITION, self._on_stop_speech_recognition, weak=False)
        self.event_bus.subscribe(Events.UPDATE_SPEECH_SETTINGS, self._on_update_speech_settings, weak=False)
        
        self.event_bus.subscribe(Events.SHOW_LOADING_POPUP, self._on_show_loading_popup, weak=False)
        self.event_bus.subscribe(Events.CLOSE_LOADING_POPUP, self._on_close_loading_popup, weak=False)

        self.event_bus.subscribe(Events.UPDATE_GAME_CONNECTION, self._on_update_game_connection, weak=False)
        self.event_bus.subscribe(Events.SET_DIALOG_ACTIVE, self._on_set_dialog_active, weak=False)
        self.event_bus.subscribe(Events.UPDATE_CHAT, self._on_update_chat, weak=False)
        self.event_bus.subscribe(Events.GET_SETTINGS, self._on_get_settings, weak=False)
        self.event_bus.subscribe(Events.CLEAR_USER_INPUT, self._on_clear_user_input, weak=False)
        self.event_bus.subscribe(Events.SET_WAITING_ANSWER, self._on_set_waiting_answer, weak=False)
        self.event_bus.subscribe(Events.SET_CONNECTED_TO_GAME, self._on_set_connected_to_game, weak=False)

    def all_settings_actions(self, key, value):
        self.settings_controller.all_settings_actions(key, value)

    def update_game_connection(self, is_connected):
        self.ConnectedToGame = is_connected
        self.event_bus.emit(Events.UPDATE_STATUS_COLORS)

    def load_api_settings(self, update_model):
        self.settings_controller.load_api_settings(update_model)

    def clear_user_input(self):
        self.user_input = ""
        self.event_bus.emit(Events.CLEAR_USER_INPUT_UI)

    def stage_image_bytes(self, img_bytes: bytes) -> int:
        fd, tmp_path = tempfile.mkstemp(suffix=".png", prefix="nm_clip_")
        os.close(fd)
        with open(tmp_path, "wb") as f:
            f.write(img_bytes)

        self.staged_images.append(tmp_path)
        logger.info(f"Clipboard image staged: {tmp_path}")
        return len(self.staged_images)

    def clear_staged_images(self):
        self.staged_images.clear()

    def init_model_thread(self, model_id, loading_window, status_label, progress):
        self.audio_controller.init_model_thread(model_id, loading_window, status_label, progress)

    def refresh_local_voice_modules(self):
        self.audio_controller.refresh_local_voice_modules()

    def check_module_installed(self, module_name):
        return self.audio_controller.check_module_installed(module_name)

    def check_available_vram(self):
        return self.audio_controller.check_available_vram()


    def close_app(self):
        logger.info("Начинаем закрытие приложения...")
        
        self.capture_controller.stop_screen_capture_thread()
        self.capture_controller.stop_camera_capture_thread()
        self.audio_controller.delete_all_sound_files()
        
        try:
            self.event_bus.emit(Events.STOP_SERVER)
        except Exception as e:
            logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        
        from handlers.asr_handler import SpeechRecognition
        SpeechRecognition.speech_recognition_stop()
        time.sleep(2)
        
        self.loop_controller.stop_loop()
        
        logger.info("Закрываемся")

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
                        import importlib
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
    
    def _on_clear_chat(self, event: Event):
        pass
    
    def _on_save_setting(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key:
            self.settings.set(key, value)
            self.settings.save_settings()
            self.all_settings_actions(key, value)
    
    def _on_get_setting(self, event: Event):
        key = event.data.get('key')
        default = event.data.get('default', None)
        
        return self.settings.get(key, default)
    
    def _on_stage_image(self, event: Event):
        image_data = event.data.get('image_data')
        if image_data:
            if isinstance(image_data, bytes):
                self.stage_image_bytes(image_data)
            elif isinstance(image_data, str):
                self.staged_images.append(image_data)
    
    def _on_clear_staged_images(self, event: Event):
        self.clear_staged_images()
    
    def _on_get_connection_status(self, event: Event):
        return self.ConnectedToGame
    
    def _on_schedule_g4f_update(self, event: Event):
        version = event.data.get('version', 'latest')
        
        try:
            self.settings.set("G4F_TARGET_VERSION", version)
            self.settings.set("G4F_UPDATE_PENDING", True)
            self.settings.set("G4F_VERSION", version)
            self.settings.save_settings()
            logger.info(f"Обновление g4f до версии '{version}' запланировано на следующий запуск.")
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении настроек для запланированного обновления: {e}", exc_info=True)
            return False
    
    def _on_request_tg_code(self, event: Event):
        code_future = event.data.get('future')
        if code_future:
            self.event_bus.emit("show_tg_code_dialog", {'future': code_future})
    
    def _on_request_tg_password(self, event: Event):
        password_future = event.data.get('future')
        if password_future:
            self.event_bus.emit("show_tg_password_dialog", {'future': password_future})
    
    def _on_set_microphone(self, event: Event):
        microphone_name = event.data.get('name')
        device_id = event.data.get('device_id')
        
        if microphone_name and device_id is not None:
            if hasattr(self, 'speech_controller'):
                self.speech_controller.selected_microphone = microphone_name
                self.speech_controller.device_id = device_id
            
            self.settings.set("NM_MICROPHONE_ID", device_id)
            self.settings.set("NM_MICROPHONE_NAME", microphone_name)
            self.settings.save_settings()
            
            logger.info(f"Выбран микрофон: {microphone_name} (ID: {device_id})")
    
    def _on_start_speech_recognition(self, event: Event):
        device_id = event.data.get('device_id', 0)
        
        try:
            from handlers.asr_handler import SpeechRecognition
            if hasattr(self, 'loop_controller') and self.loop_controller.loop:
                SpeechRecognition.speech_recognition_start(device_id, self.loop_controller.loop)
                logger.info("Распознавание речи запущено")
        except Exception as e:
            logger.error(f"Ошибка запуска распознавания речи: {e}")
    
    def _on_stop_speech_recognition(self, event: Event):
        try:
            from handlers.asr_handler import SpeechRecognition
            SpeechRecognition.speech_recognition_stop()
            logger.info("Распознавание речи остановлено")
        except Exception as e:
            logger.error(f"Ошибка остановки распознавания речи: {e}")
    
    def _on_update_speech_settings(self, event: Event):
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key and hasattr(self, 'speech_controller'):
            self.speech_controller.update_speech_settings(key, value)
    
    def _on_show_loading_popup(self, event: Event):
        message = event.data.get('message', 'Loading...')
        self.event_bus.emit("display_loading_popup", {"message": message})
    
    def _on_close_loading_popup(self, event: Event):
        self.event_bus.emit("hide_loading_popup")

    def _on_get_user_input(self, event: Event):
        return self.gui_controller.get_user_input()

    def _on_update_game_connection(self, event: Event):
        is_connected = event.data.get('is_connected', False)
        self.update_game_connection(is_connected)

    def _on_set_dialog_active(self, event: Event):
        self.dialog_active = event.data.get('active', False)

    def _on_update_chat(self, event: Event):
        role = event.data.get('role', '')
        content = event.data.get('content', '')
        is_initial = event.data.get('is_initial', False)
        emotion = event.data.get('emotion', '')
        
        self.event_bus.emit(Events.UPDATE_CHAT_UI, {
            'role': role,
            'response': content,
            'is_initial': is_initial,
            'emotion': emotion
        })

    def _on_get_settings(self, event: Event):
        return self.settings.settings

    def _on_clear_user_input(self, event: Event):
        self.clear_user_input()

    def _on_set_waiting_answer(self, event: Event):
        self.audio_controller.waiting_answer = event.data.get('waiting', False)

    def _on_set_connected_to_game(self, event: Event):
        self.ConnectedToGame = event.data.get('connected', False)

    @property
    def loop(self):
        return self.loop_controller.loop