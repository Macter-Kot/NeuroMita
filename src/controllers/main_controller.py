import os
import asyncio
import threading
import tempfile
import time
from pathlib import Path
from PyQt6.QtCore import QTimer

from controllers.audio_controller import AudioController
from controllers.telegram_controller import TelegramController
from controllers.capture_controller import CaptureController
from controllers.model_controller import ModelController
from controllers.speech_controller import SpeechController
from controllers.server_controller import ServerController
from controllers.settings_controller import SettingsController

from main_logger import logger
from utils.ffmpeg_installer import install_ffmpeg
from utils.pip_installer import PipInstaller

class MainController:
    def __init__(self, view):
        self.view = view
        
        self.voice_language_var = None
        self.local_voice_combobox = None
        self.debug_window = None
        self.mic_combobox = None

        self.ConnectedToGame = False
        self.chat_window = None
        self.token_count_label = None

        self.user_entry = None
        self.user_input = ""

        self.api_key = ""
        self.api_key_res = ""
        self.api_url = ""
        self.api_model = ""
        self.makeRequest = False

        self.instant_send = False
        self.dialog_active = False

        self.lazy_load_batch_size = 50
        self.total_messages_in_history = 0
        self.loaded_messages_offset = 0
        self.loading_more_history = False

        self.staged_images = []
        self.attachment_label = None
        self.attach_button = None
        self.send_screen_button = None

        self.ffmpeg_install_popup = None
        
        self.game_connected_checkbox_var = False
        
        self.loop_ready_event = threading.Event()
        self.loop = None
        self.asyncio_thread = threading.Thread(target=self.start_asyncio_loop, daemon=True)
        self.asyncio_thread.start()

        try:
            target_folder = "Settings"
            os.makedirs(target_folder, exist_ok=True)
            self.config_path = os.path.join(target_folder, "settings.json")

            self.settings_controller = SettingsController(self, self.config_path)
            self.settings = self.settings_controller.settings
            self.settings_controller.load_api_settings(False)
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
        self.telegram_controller = TelegramController(self)
        self.model_controller = ModelController(self, self.api_key, self.api_key_res, self.api_url, 
                                               self.api_model, self.makeRequest, self.pip_installer)
        self.capture_controller = CaptureController(self)
        self.speech_controller = SpeechController(self)
        self.server_controller = ServerController(self)

        QTimer.singleShot(100, self.check_and_install_ffmpeg)

        self.audio_controller.delete_all_sound_files()

        self.telegram_controller.start_silero_async()

    def connect_view_signals(self):
        self.telegram_controller.connect_view_signals()

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
                logger.info("Начинаем shutdown asyncio loop...")
                pending = asyncio.all_tasks(self.loop)
                for task in pending:
                    task.cancel()
                try:
                    self.loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception as e:
                    logger.error(f"Ошибка при завершении pending tasks: {e}")
                self.loop.close()
                logger.info("Цикл событий asyncio закрыт.")
        except Exception as e:
            logger.info(f"Ошибка при запуске цикла событий asyncio: {e}")
            self.loop_ready_event.set()

    def all_settings_actions(self, key, value):
        self.settings_controller.all_settings_actions(key, value)

    def check_text_to_talk_or_send(self):
        self.speech_controller.check_text_to_talk_or_send()

    def update_game_connection(self, is_connected):
        self.ConnectedToGame = is_connected
        QTimer.singleShot(0, self.update_status_colors)

    def load_api_settings(self, update_model):
        self.settings_controller.load_api_settings(update_model)

    def clear_user_input(self):
        self.user_input = ""
        self.view.user_entry.clear()

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

    async def async_send_message(
        self,
        user_input: str,
        system_input: str = "",
        image_data: list[bytes] | None = None
    ):
        try:
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
                    lambda: self.model_controller.model.generate_response(
                        user_input=user_input,
                        system_input=system_input,
                        image_data=image_data,
                        stream_callback=stream_callback_handler if is_streaming else None
                    )
                ),
                timeout=120.0
            )

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

            if self.server_controller.server and self.server_controller.server.client_socket:
                final_response_text = response if response else "..."
                try:
                    self.server_controller.server.send_message_to_server(final_response_text)
                    logger.info("Ответ отправлен в игру.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ в игру: {e}")
                    
        except asyncio.TimeoutError:
            logger.warning("Тайм-аут: генерация ответа заняла слишком много времени.")
            self.show_mita_error("Превышено время ожидания ответа")
        except Exception as e:
            logger.error(f"Ошибка в async_send_message: {e}", exc_info=True)
            self.show_mita_error(f"Ошибка: {str(e)[:50]}...")

    def init_model_thread(self, model_id, loading_window, status_label, progress):
        self.model_controller.init_model_thread(model_id, loading_window, status_label, progress)

    def refresh_local_voice_modules(self):
        self.model_controller.refresh_local_voice_modules()

    def check_module_installed(self, module_name):
        return self.model_controller.check_module_installed(module_name)

    def check_available_vram(self):
        return self.model_controller.check_available_vram()

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
        logger.info("Начинаем закрытие приложения...")
        
        self.capture_controller.stop_screen_capture_thread()
        self.capture_controller.stop_camera_capture_thread()
        self.audio_controller.delete_all_sound_files()
        
        # Остановка сервера с обработкой ошибок
        try:
            self.server_controller.stop_server()
        except Exception as e:
            logger.error(f"Ошибка при остановке сервера: {e}", exc_info=True)
        
        # Остановка распознавания речи
        from handlers.asr_handler import SpeechRecognition
        SpeechRecognition.speech_recognition_stop()
        time.sleep(2)  # Увеличенное ожидание для завершения задач
        
        # Остановка asyncio loop
        if self.loop and not self.loop.is_closed():
            logger.info("Остановка asyncio loop...")
            try:
                # Shutdown default executor для предотвращения ошибок futures
                if self.loop.is_running():
                    self.loop.run_until_complete(self.loop.shutdown_default_executor())
                
                self.loop.call_soon_threadsafe(self.loop.stop)
                self.loop.run_forever()  # Чтобы обработать stop
            except Exception as e:
                logger.error(f"Ошибка при shutdown loop: {e}")
            finally:
                if not self.loop.is_closed():
                    self.loop.close()
                logger.info("Asyncio loop остановлен.")
        
        if self.asyncio_thread.is_alive():
            self.asyncio_thread.join(timeout=5)
            if self.asyncio_thread.is_alive():
                logger.warning("Asyncio thread didn't stop in time.")
        
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

    @property
    def update_debug_signal(self):
        if self.view:
            return self.view.update_debug_signal
        return None

    @property
    def update_chat_signal(self):
        if self.view:
            return self.view.update_chat_signal
        return None

    @property
    def update_status_signal(self):
        if self.view:
            return self.view.update_status_signal
        return None

    @property
    def prepare_stream_signal(self):
        if self.view:
            return self.view.prepare_stream_signal
        return None

    @property
    def append_stream_chunk_signal(self):
        if self.view:
            return self.view.append_stream_chunk_signal
        return None

    @property
    def finish_stream_signal(self):
        if self.view:
            return self.view.finish_stream_signal
        return None
    
    def show_mita_thinking(self):
        print("[DEBUG] Controller: запрос на показ статуса 'думает'")
        if self.view and hasattr(self.view, 'show_thinking_signal'):
            character_name = self.model_controller.model.current_character.name if self.model_controller.model.current_character else "Мита"
            self.view.show_thinking_signal.emit(character_name)
        else:
            print("[DEBUG] view или show_thinking_signal не найден!")
            
    def show_mita_error(self, error_message):
        print(f"[DEBUG] Controller: запрос на показ ошибки: {error_message}")
        if self.view and hasattr(self.view, 'show_error_signal'):
            self.view.show_error_signal.emit(error_message)
            
    def hide_mita_status(self):
        print("[DEBUG] Controller: запрос на скрытие статуса")
        if self.view and hasattr(self.view, 'hide_status_signal'):
            self.view.hide_status_signal.emit()
        else:
            print("[DEBUG] view или hide_status_signal не найден при попытке скрыть!")

    def show_mita_error_pulse(self):
        if self.view and hasattr(self.view, 'pulse_error_signal'):
            self.view.pulse_error_signal.emit()

    def update_status_colors(self):
        if self.view:
            self.view.update_status_colors()

    # Делегирующие свойства для обратной совместимости
    @property
    def silero_connected(self):
        return self.telegram_controller.silero_connected
    
    @silero_connected.setter
    def silero_connected(self, value):
        self.telegram_controller.silero_connected = value
    
    @property
    def bot_handler(self):
        return self.telegram_controller.bot_handler
    
    @bot_handler.setter
    def bot_handler(self, value):
        self.telegram_controller.bot_handler = value
    
    @property
    def bot_handler_ready(self):
        return self.telegram_controller.bot_handler_ready
    
    @bot_handler_ready.setter 
    def bot_handler_ready(self, value):
        self.telegram_controller.bot_handler_ready = value
    
    @property
    def mic_recognition_active(self):
        return self.speech_controller.mic_recognition_active
    
    @mic_recognition_active.setter
    def mic_recognition_active(self, value):
        self.speech_controller.mic_recognition_active = value
    
    @property
    def screen_capture_active(self):
        return self.capture_controller.screen_capture_active
    
    @screen_capture_active.setter
    def screen_capture_active(self, value):
        self.capture_controller.screen_capture_active = value
    
    @property
    def camera_capture_active(self):
        return self.capture_controller.camera_capture_active
    
    @camera_capture_active.setter
    def camera_capture_active(self, value):
        self.capture_controller.camera_capture_active = value
    
    @property
    def screen_capture_instance(self):
        return self.capture_controller.screen_capture_instance
    
    @property
    def image_request_timer_running(self):
        return self.capture_controller.image_request_timer_running
    
    @property
    def last_image_request_time(self):
        return self.capture_controller.last_image_request_time
    
    @last_image_request_time.setter
    def last_image_request_time(self, value):
        self.capture_controller.last_image_request_time = value
    
    @property
    def textToTalk(self):
        return self.audio_controller.textToTalk
    
    @textToTalk.setter
    def textToTalk(self, value):
        self.audio_controller.textToTalk = value
    
    @property
    def waiting_answer(self):
        return self.audio_controller.waiting_answer
    
    @waiting_answer.setter
    def waiting_answer(self, value):
        self.audio_controller.waiting_answer = value
    
    @property
    def local_voice(self):
        return self.audio_controller.local_voice
    
    @property
    def model(self):
        return self.model_controller.model
    
    @property
    def server(self):
        return self.server_controller.server
    
    @property
    def device_id(self):
        return self.speech_controller.device_id
    
    @device_id.setter
    def device_id(self, value):
        self.speech_controller.device_id = value
    
    @property
    def selected_microphone(self):
        return self.speech_controller.selected_microphone
    
    @selected_microphone.setter
    def selected_microphone(self, value):
        self.speech_controller.selected_microphone = value
    
    @property
    def patch_to_sound_file(self):
        return self.audio_controller.patch_to_sound_file
    
    @patch_to_sound_file.setter
    def patch_to_sound_file(self, value):
        self.audio_controller.patch_to_sound_file = value
    
    @property
    def id_sound(self):
        return self.audio_controller.id_sound
    
    @id_sound.setter
    def id_sound(self, value):
        self.audio_controller.id_sound = value
    
    @property
    def voiceover_method(self):
        return self.audio_controller.voiceover_method
    
    @voiceover_method.setter
    def voiceover_method(self, value):
        self.audio_controller.voiceover_method = value
    
    @property
    def current_local_voice_id(self):
        return self.audio_controller.current_local_voice_id
    
    @current_local_voice_id.setter
    def current_local_voice_id(self, value):
        self.audio_controller.current_local_voice_id = value
    
    @property
    def last_voice_model_selected(self):
        return self.audio_controller.last_voice_model_selected
    
    @last_voice_model_selected.setter
    def last_voice_model_selected(self, value):
        self.audio_controller.last_voice_model_selected = value
    
    @property
    def model_loading_cancelled(self):
        return self.audio_controller.model_loading_cancelled
    
    @model_loading_cancelled.setter
    def model_loading_cancelled(self, value):
        self.audio_controller.model_loading_cancelled = value

    @property
    def stop_screen_capture_thread(self):
        return self.capture_controller.stop_screen_capture_thread
    
    @property
    def stop_camera_capture_thread(self):
        return self.capture_controller.stop_camera_capture_thread
    
    @property
    def delete_all_sound_files(self):
        return self.audio_controller.delete_all_sound_files
    
    @property 
    def stop_server(self):
        return self.server_controller.stop_server
    
    @property
    def camera_capture(self):
        return self.capture_controller.camera_capture
    
    @camera_capture.setter
    def camera_capture(self, value):
        self.capture_controller.camera_capture = value