import os
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

        self.dialog_active = False


        self.loop_controller = LoopController()
        logger.warning("LoopController успешно инициализирован.")

        self.gui_controller = None

        self.telegram_controller = TelegramController()
        logger.warning("TelegramController успешно инициализирован.")
        

        try:
            target_folder = "Settings"
            os.makedirs(target_folder, exist_ok=True)
            self.config_path = os.path.join(target_folder, "settings.json")

            self.settings_controller = SettingsController(self.config_path)
            self.settings = self.settings_controller.settings
        except Exception as e:
            logger.info("Не удалось удачно получить из системных переменных все данные", e)
            self.settings = SettingsController("Settings/settings.json").settings

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
        self.model_controller = ModelController(self.settings, self.pip_installer)
        logger.warning("ModelController успешно инициализирован.")
        self.capture_controller = CaptureController(self.settings)
        logger.warning("CaptureController успешно инициализирован.")
        self.speech_controller = SpeechController()
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
            # в этой логике надо добавить автоподключение.
            if self.settings.get('VOICEOVER_METHOD') == 'TG' and self.settings.get('USE_VOICEOVER', False):
                self.telegram_controller.start_silero_async()
    
    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.SCHEDULE_G4F_UPDATE, self._on_schedule_g4f_update, weak=False)
        
        self.event_bus.subscribe(Events.REQUEST_TG_CODE, self._on_request_tg_code, weak=False)
        self.event_bus.subscribe(Events.REQUEST_TG_PASSWORD, self._on_request_tg_password, weak=False)
        
        self.event_bus.subscribe(Events.SHOW_LOADING_POPUP, self._on_show_loading_popup, weak=False)
        self.event_bus.subscribe(Events.CLOSE_LOADING_POPUP, self._on_close_loading_popup, weak=False)

        self.event_bus.subscribe(Events.SET_DIALOG_ACTIVE, self._on_set_dialog_active, weak=False)

    def close_app(self):
        logger.info("Начинаем закрытие приложения...")
        
        self.capture_controller.stop_screen_capture_thread()
        self.capture_controller.stop_camera_capture_thread()
        self.audio_controller.delete_all_sound_files()
        
        try:
            self.event_bus.emit(Events.STOP_SERVER)
        except Exception as e:
            logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        
        self.event_bus.emit(Events.STOP_SPEECH_RECOGNITION)
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
    
    def _on_show_loading_popup(self, event: Event):
        message = event.data.get('message', 'Loading...')
        self.event_bus.emit("display_loading_popup", {"message": message})
    
    def _on_close_loading_popup(self, event: Event):
        self.event_bus.emit("hide_loading_popup")

    def _on_set_dialog_active(self, event: Event):
        self.dialog_active = event.data.get('active', False)
    