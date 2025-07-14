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

        self.instant_send = False
        self.dialog_active = False

        self.lazy_load_batch_size = 50
        self.total_messages_in_history = 0
        self.loaded_messages_offset = 0
        self.loading_more_history = False

        self.staged_images = []

        self.loop_ready_event = threading.Event()
        self.loop = None
        self.llm_processing = False
        self.asyncio_thread = threading.Thread(target=self.start_asyncio_loop, daemon=True)
        self.asyncio_thread.start()

        self.gui_controller = None

        self.telegram_controller = TelegramController(self)
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
        self.capture_controller = CaptureController(self)
        logger.warning("CaptureController успешно инициализирован.")
        self.speech_controller = SpeechController(self)
        logger.warning("SpeechController успешно инициализирован.")
        self.server_controller = ServerController(self)
        logger.warning("ServerController успешно инициализирован.")

        

        self.audio_controller.delete_all_sound_files()

        self.telegram_controller.start_silero_async()
        
        # Подписываемся на события
        self._subscribe_to_events()
        logger.info("MainController подписался на события")
        
        # Инициализация состояния для моделей
        self.model_loading_cancelled = False
        
        # Запускаем периодические проверки
        self.start_periodic_checks()

    def update_view(self, view):
        if not self.gui_controller:
            self.view = view
            self.gui_controller = GuiController(self, view)
            logger.warning("GuiController успешно инициализирован.")
            self.settings_controller.load_api_settings(False)

    def connect_view_signals(self):
        self.gui_controller.connect_view_signals()
    
    def _subscribe_to_events(self):
        """Подписка на все необходимые события"""
        # Сообщения
        self.event_bus.subscribe(Events.SEND_MESSAGE, self._on_send_message, weak=False)
        self.event_bus.subscribe(Events.CLEAR_CHAT, self._on_clear_chat, weak=False)
        self.event_bus.subscribe(Events.LOAD_HISTORY, self._on_load_history, weak=False)
        self.event_bus.subscribe(Events.LOAD_MORE_HISTORY, self._on_load_more_history, weak=False)
        
        # Настройки
        self.event_bus.subscribe(Events.SAVE_SETTING, self._on_save_setting, weak=False)
        self.event_bus.subscribe(Events.GET_SETTING, self._on_get_setting, weak=False)
        
        # Изображения
        self.event_bus.subscribe(Events.STAGE_IMAGE, self._on_stage_image, weak=False)
        self.event_bus.subscribe(Events.CLEAR_STAGED_IMAGES, self._on_clear_staged_images, weak=False)
        self.event_bus.subscribe(Events.CAPTURE_SCREEN, self._on_capture_screen, weak=False)
        self.event_bus.subscribe(Events.GET_CAMERA_FRAMES, self._on_get_camera_frames, weak=False)
        
        # Голосовые модели
        self.event_bus.subscribe(Events.SELECT_VOICE_MODEL, self._on_select_voice_model, weak=False)
        self.event_bus.subscribe(Events.INIT_VOICE_MODEL, self._on_init_voice_model, weak=False)
        self.event_bus.subscribe(Events.CHECK_MODEL_INSTALLED, self._on_check_model_installed, weak=False)
        self.event_bus.subscribe(Events.CHECK_MODEL_INITIALIZED, self._on_check_model_initialized, weak=False)
        self.event_bus.subscribe(Events.CHANGE_VOICE_LANGUAGE, self._on_change_voice_language, weak=False)
        self.event_bus.subscribe(Events.REFRESH_VOICE_MODULES, self._on_refresh_voice_modules, weak=False)
        
        # Статусы
        self.event_bus.subscribe(Events.GET_CONNECTION_STATUS, self._on_get_connection_status, weak=False)
        self.event_bus.subscribe(Events.GET_SILERO_STATUS, self._on_get_silero_status, weak=False)
        self.event_bus.subscribe(Events.GET_MIC_STATUS, self._on_get_mic_status, weak=False)
        self.event_bus.subscribe(Events.GET_SCREEN_CAPTURE_STATUS, self._on_get_screen_capture_status, weak=False)
        self.event_bus.subscribe(Events.GET_CAMERA_CAPTURE_STATUS, self._on_get_camera_capture_status, weak=False)
        
        # Управление
        self.event_bus.subscribe(Events.STOP_SCREEN_CAPTURE, self._on_stop_screen_capture, weak=False)
        self.event_bus.subscribe(Events.STOP_CAMERA_CAPTURE, self._on_stop_camera_capture, weak=False)
        self.event_bus.subscribe(Events.DELETE_SOUND_FILES, self._on_delete_sound_files, weak=False)
        self.event_bus.subscribe(Events.STOP_SERVER, self._on_stop_server, weak=False)
        
        # Проверки
        self.event_bus.subscribe(Events.CHECK_TEXT_TO_TALK, self._on_check_text_to_talk, weak=False)
        self.event_bus.subscribe(Events.GET_CHARACTER_NAME, self._on_get_character_name, weak=False)
        self.event_bus.subscribe(Events.GET_CURRENT_CONTEXT_TOKENS, self._on_get_current_context_tokens, weak=False)
        self.event_bus.subscribe(Events.CALCULATE_COST, self._on_calculate_cost, weak=False)
        
        # G4F
        self.event_bus.subscribe(Events.SCHEDULE_G4F_UPDATE, self._on_schedule_g4f_update, weak=False)
        
        # Telegram
        self.event_bus.subscribe(Events.REQUEST_TG_CODE, self._on_request_tg_code, weak=False)
        self.event_bus.subscribe(Events.REQUEST_TG_PASSWORD, self._on_request_tg_password, weak=False)

        # Персонажи
        self.event_bus.subscribe(Events.GET_ALL_CHARACTERS, self._on_get_all_characters, weak=False)
        self.event_bus.subscribe(Events.GET_CURRENT_CHARACTER, self._on_get_current_character, weak=False)
        self.event_bus.subscribe(Events.SET_CHARACTER_TO_CHANGE, self._on_set_character_to_change, weak=False)
        self.event_bus.subscribe(Events.CHECK_CHANGE_CHARACTER, self._on_check_change_character, weak=False)
        self.event_bus.subscribe(Events.GET_CHARACTER, self._on_get_character, weak=False)
        self.event_bus.subscribe(Events.RELOAD_CHARACTER_DATA, self._on_reload_character_data, weak=False)
        self.event_bus.subscribe(Events.RELOAD_CHARACTER_PROMPTS, self._on_reload_character_prompts, weak=False)
        self.event_bus.subscribe(Events.CLEAR_CHARACTER_HISTORY, self._on_clear_character_history, weak=False)
        self.event_bus.subscribe(Events.CLEAR_ALL_HISTORIES, self._on_clear_all_histories, weak=False)
        
        # Микрофон
        self.event_bus.subscribe(Events.SET_MICROPHONE, self._on_set_microphone, weak=False)
        self.event_bus.subscribe(Events.START_SPEECH_RECOGNITION, self._on_start_speech_recognition, weak=False)
        self.event_bus.subscribe(Events.STOP_SPEECH_RECOGNITION, self._on_stop_speech_recognition, weak=False)
        self.event_bus.subscribe(Events.UPDATE_SPEECH_SETTINGS, self._on_update_speech_settings, weak=False)
        
        # Асинхронные операции
        self.event_bus.subscribe(Events.GET_EVENT_LOOP, self._on_get_event_loop, weak=False)
        self.event_bus.subscribe(Events.RELOAD_PROMPTS_ASYNC, self._on_reload_prompts_async, weak=False)
        
        # Загрузка
        self.event_bus.subscribe(Events.SHOW_LOADING_POPUP, self._on_show_loading_popup, weak=False)
        self.event_bus.subscribe(Events.CLOSE_LOADING_POPUP, self._on_close_loading_popup, weak=False)

        # Отладка
        self.event_bus.subscribe(Events.GET_DEBUG_INFO, self._on_get_debug_info, weak=False)

        # От chat_handler.py
        self.event_bus.subscribe(Events.SET_TTS_DATA, self._on_set_tts_data, weak=False)

        # От server.py:
        self.event_bus.subscribe(Events.UPDATE_GAME_CONNECTION, self._on_update_game_connection, weak=False)
        self.event_bus.subscribe(Events.SET_CHARACTER_TO_CHANGE, self._on_set_character_to_change_server, weak=False)
        self.event_bus.subscribe(Events.SET_GAME_DATA, self._on_set_game_data, weak=False)
        self.event_bus.subscribe(Events.SET_DIALOG_ACTIVE, self._on_set_dialog_active, weak=False)
        self.event_bus.subscribe(Events.ADD_TEMPORARY_SYSTEM_INFO, self._on_add_temporary_system_info, weak=False)
        self.event_bus.subscribe(Events.SET_ID_SOUND, self._on_set_id_sound, weak=False)
        self.event_bus.subscribe(Events.UPDATE_CHAT, self._on_update_chat, weak=False)
        self.event_bus.subscribe(Events.GET_SERVER_DATA, self._on_get_server_data, weak=False)
        self.event_bus.subscribe(Events.GET_SETTINGS, self._on_get_settings, weak=False)
        self.event_bus.subscribe(Events.RESET_SERVER_DATA, self._on_reset_server_data, weak=False)
        self.event_bus.subscribe(Events.CLEAR_USER_INPUT, self._on_clear_user_input, weak=False)
        self.event_bus.subscribe(Events.SET_WAITING_ANSWER, self._on_set_waiting_answer, weak=False)
        self.event_bus.subscribe(Events.GENERATE_RESPONSE, self._on_generate_response, weak=False)
        self.event_bus.subscribe(Events.SET_CONNECTED_TO_GAME, self._on_set_connected_to_game, weak=False)

        # От telegram_handler.py:
        self.event_bus.subscribe(Events.SET_SOUND_FILE_DATA, self._on_set_sound_file_data, weak=False)
        self.event_bus.subscribe(Events.SET_SILERO_CONNECTED, self._on_set_silero_connected, weak=False)

        # От capture_controller.py:
        self.event_bus.subscribe("send_periodic_image_request", self._on_send_periodic_image_request, weak=False)


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

    async def async_send_message(
        self,
        user_input: str,
        system_input: str = "",
        image_data: list[bytes] | None = None
    ):
        try:
            print("[DEBUG] Начинаем async_send_message, показываем статус")
            self.llm_processing = True  # Устанавливаем флаг
            
            is_streaming = bool(self.settings.get("ENABLE_STREAMING", False))

            def stream_callback_handler(chunk: str):
                self.event_bus.emit(Events.APPEND_STREAM_CHUNK_UI, {'chunk': chunk})

            if is_streaming:
                self.event_bus.emit(Events.PREPARE_STREAM_UI)

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
                timeout=600.0
            )

            if is_streaming:
                self.event_bus.emit(Events.FINISH_STREAM_UI)
            else:
                self.event_bus.emit(Events.UPDATE_CHAT_UI, {
                    'role': 'assistant',
                    'response': response if response is not None else "...",
                    'is_initial': False,
                    'emotion': ''
                })

            self.event_bus.emit(Events.UPDATE_STATUS)
            self.event_bus.emit(Events.UPDATE_DEBUG_INFO)
            self.event_bus.emit(Events.UPDATE_TOKEN_COUNT)

            if self.server_controller.server and self.server_controller.server.client_socket:
                final_response_text = response if response else "..."
                try:
                    self.server_controller.server.send_message_to_server(final_response_text)
                    logger.info("Ответ отправлен в игру.")
                except Exception as e:
                    logger.error(f"Не удалось отправить ответ в игру: {e}")
            
            self.llm_processing = False  # Сбрасываем флаг после успешной обработки
                    
        except asyncio.TimeoutError:
            logger.warning("Тайм-аут: генерация ответа заняла слишком много времени.")
            self.llm_processing = False  # Сбрасываем флаг при таймауте
            self.event_bus.emit(Events.ON_FAILED_RESPONSE, {'error': "Превышено время ожидания ответа"})
        except Exception as e:
            logger.error(f"Ошибка в async_send_message: {e}", exc_info=True)
            self.llm_processing = False  # Сбрасываем флаг при ошибке
            self.event_bus.emit(Events.ON_FAILED_RESPONSE, {'error': f"Ошибка: {str(e)[:50]}..."})

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
    
    # region Обработчики событий - Сообщения
    
    def _on_send_message(self, event: Event):
        """Обработка отправки сообщения"""
        data = event.data
        user_input = data.get('user_input', '')
        system_input = data.get('system_input', '')
        image_data = data.get('image_data', [])
        
        # Обновляем время последнего запроса изображения
        if image_data:
            self.last_image_request_time = time.time()
        
        # Отправляем сообщение асинхронно
        
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.async_send_message(user_input, system_input, image_data),
                self.loop
            )
    
    def _on_clear_chat(self, event: Event):
        """Очистка чата"""
        # Здесь может быть дополнительная логика очистки на стороне контроллера
        pass
    
    def _on_load_history(self, event: Event):
        """Загрузка истории чата"""
        self.loaded_messages_offset = 0
        self.total_messages_in_history = 0
        self.loading_more_history = False
        
        chat_history = self.model.current_character.load_history()
        all_messages = chat_history["messages"]
        self.total_messages_in_history = len(all_messages)
        
        max_display_messages = int(self.settings.get("MAX_CHAT_HISTORY_DISPLAY", 100))
        start_index = max(0, self.total_messages_in_history - max_display_messages)
        messages_to_load = all_messages[start_index:]
        
        self.loaded_messages_offset = len(messages_to_load)
        
        # Отправляем данные обратно во View
        self.event_bus.emit("history_loaded", {
            'messages': messages_to_load,
            'total_messages': self.total_messages_in_history,
            'loaded_offset': self.loaded_messages_offset
        })
    
    def _on_load_more_history(self, event: Event):
        """Загрузка дополнительной истории"""
        if self.loaded_messages_offset >= self.total_messages_in_history:
            return
        
        self.loading_more_history = True
        try:
            chat_history = self.model.current_character.load_history()
            all_messages = chat_history["messages"]
            
            lazy_load_batch_size = getattr(self, 'lazy_load_batch_size', 50)
            end_index = self.total_messages_in_history - self.loaded_messages_offset
            start_index = max(0, end_index - lazy_load_batch_size)
            messages_to_prepend = all_messages[start_index:end_index]
            
            if messages_to_prepend:
                self.loaded_messages_offset += len(messages_to_prepend)
                
                # Отправляем данные обратно во View
                self.event_bus.emit("more_history_loaded", {
                    'messages': messages_to_prepend,
                    'loaded_offset': self.loaded_messages_offset
                })
        finally:
            self.loading_more_history = False
    
    # endregion
    
    # region Обработчики событий - Настройки
    
    def _on_save_setting(self, event: Event):
        """Сохранение настройки"""
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key:
            self.settings.set(key, value)
            self.settings.save_settings()
            self.all_settings_actions(key, value)
    
    def _on_get_setting(self, event: Event):
        """Получение значения настройки"""
        key = event.data.get('key')
        default = event.data.get('default', None)
        
        return self.settings.get(key, default)
    
    # endregion
    
    # region Обработчики событий - Изображения
    
    def _on_stage_image(self, event: Event):
        """Добавление изображения в очередь"""
        image_data = event.data.get('image_data')
        if image_data:
            if isinstance(image_data, bytes):
                self.stage_image_bytes(image_data)
            elif isinstance(image_data, str):
                self.staged_images.append(image_data)
    
    def _on_clear_staged_images(self, event: Event):
        """Очистка очереди изображений"""
        self.clear_staged_images()
    
    def _on_capture_screen(self, event: Event):
        """Захват экрана"""
        history_limit = event.data.get('limit', 1) if event.data else 1
        
        if hasattr(self, 'screen_capture_instance'):
            frames = self.screen_capture_instance.get_recent_frames(history_limit)
            return frames
        return []
    
    def _on_get_camera_frames(self, event: Event):
        """Получение кадров с камеры"""
        history_limit = event.data.get('limit', 1) if event.data else 1
        
        if (hasattr(self, 'camera_capture') and 
            self.camera_capture is not None and 
            self.camera_capture.is_running()):
            frames = self.camera_capture.get_recent_frames(history_limit)
            return frames
        return []
    
    # endregion
    
    # region Обработчики событий - Голосовые модели
    
    def _on_select_voice_model(self, event: Event):
        """Выбор голосовой модели"""
        model_id = event.data.get('model_id')
        if model_id and hasattr(self, 'local_voice'):
            try:
                self.local_voice.select_model(model_id)
                self.settings.set("NM_CURRENT_VOICEOVER", model_id)
                self.settings.save_settings()
                self.current_local_voice_id = model_id
                return True
            except Exception as e:
                logger.error(f'Не удалось активировать модель {model_id}: {e}')
                return False
        return False
    
    def _on_init_voice_model(self, event: Event):
        """Инициализация голосовой модели"""
        model_id = event.data.get('model_id')
        progress_callback = event.data.get('progress_callback')
        
        if model_id:
            # Запускаем инициализацию в отдельном потоке
            import threading
            thread = threading.Thread(
                target=self._init_model_thread,
                args=(model_id, progress_callback),
                daemon=True
            )
            thread.start()
    
    def _init_model_thread(self, model_id: str, progress_callback=None):
        """Поток инициализации модели"""
        try:
            if progress_callback:
                progress_callback("status", "Инициализация модели...")
            
            # Здесь должна быть реальная инициализация
            # Для примера используем заглушку
            success = self.local_voice.init_model(model_id)
            
            if success and not self.model_loading_cancelled:
                self.event_bus.emit("model_initialized", {'model_id': model_id})
            elif self.model_loading_cancelled:
                self.event_bus.emit("model_init_cancelled", {'model_id': model_id})
            else:
                self.event_bus.emit("model_init_failed", {'model_id': model_id})
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации модели {model_id}: {e}")
            self.event_bus.emit("model_init_failed", {
                'model_id': model_id, 
                'error': str(e)
            })
    
    def _on_check_model_installed(self, event: Event):
        """Проверка установлена ли модель"""
        model_id = event.data.get('model_id')
        if model_id and hasattr(self, 'local_voice'):
            return self.local_voice.is_model_installed(model_id)
        return False
    
    def _on_check_model_initialized(self, event: Event):
        """Проверка инициализирована ли модель"""
        model_id = event.data.get('model_id')
        if model_id and hasattr(self, 'local_voice'):
            return self.local_voice.is_model_initialized(model_id)
        return False
    
    def _on_change_voice_language(self, event: Event):
        """Изменение языка озвучки"""
        language = event.data.get('language')
        if language and hasattr(self.local_voice, 'change_voice_language'):
            try:
                self.local_voice.change_voice_language(language)
                return True
            except Exception as e:
                logger.error(f"Ошибка при изменении языка озвучки: {e}")
                return False
        return False
    
    def _on_refresh_voice_modules(self, event: Event):
        """Обновление голосовых модулей"""
        if hasattr(self, 'refresh_local_voice_modules'):
            self.refresh_local_voice_modules()
    
    # endregion
    
    # region Обработчики событий - Статусы
    
    def _on_get_connection_status(self, event: Event):
        """Получение статуса подключения к игре"""
        return self.ConnectedToGame
    
    def _on_get_silero_status(self, event: Event):
        """Получение статуса Silero"""
        return self.silero_connected
    
    def _on_get_mic_status(self, event: Event):
        """Получение статуса микрофона"""
        return self.mic_recognition_active
    
    def _on_get_screen_capture_status(self, event: Event):
        """Получение статуса захвата экрана"""
        return self.screen_capture_active
    
    def _on_get_camera_capture_status(self, event: Event):
        """Получение статуса захвата камеры"""
        return self.camera_capture_active
    
    # endregion
    
    # region Обработчики событий - Управление
    
    def _on_stop_screen_capture(self, event: Event):
        """Остановка захвата экрана"""
        self.stop_screen_capture_thread()
    
    def _on_stop_camera_capture(self, event: Event):
        """Остановка захвата камеры"""
        self.stop_camera_capture_thread()
    
    def _on_delete_sound_files(self, event: Event):
        """Удаление звуковых файлов"""
        self.delete_all_sound_files()
    
    def _on_stop_server(self, event: Event):
        """Остановка сервера"""
        self.stop_server()
    
    # endregion
    
    # region Обработчики событий - Проверки
    
    def _on_check_text_to_talk(self, event: Event):
        """Проверка текста для озвучки"""
        self.check_text_to_talk_or_send()
    
    def _on_get_character_name(self, event: Event):
        """Получение имени персонажа"""
        return self.model.current_character.name
    
    def _on_get_current_context_tokens(self, event: Event):
        """Получение количества токенов текущего контекста"""
        if hasattr(self.model, 'get_current_context_token_count'):
            return self.model.get_current_context_token_count()
        return 0
    
    def _on_calculate_cost(self, event: Event):
        """Расчет стоимости"""
        # Обновляем параметры модели из настроек
        self.model.token_cost_input = float(self.settings.get("TOKEN_COST_INPUT", 0.000001))
        self.model.token_cost_output = float(self.settings.get("TOKEN_COST_OUTPUT", 0.000002))
        self.model.max_model_tokens = int(self.settings.get("MAX_MODEL_TOKENS", 32000))
        
        if hasattr(self.model, 'calculate_cost_for_current_context'):
            return self.model.calculate_cost_for_current_context()
        return 0.0
    
    # endregion
    
    # region Обработчики событий - G4F
    
    def _on_schedule_g4f_update(self, event: Event):
        """Планирование обновления G4F"""
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
    
    # endregion
    
    # region Обработчики событий - Telegram
    
    def _on_request_tg_code(self, event: Event):
        """Запрос кода Telegram"""
        code_future = event.data.get('future')
        if code_future:
            # Отправляем событие для показа диалога
            self.event_bus.emit("show_tg_code_dialog", {'future': code_future})
    
    def _on_request_tg_password(self, event: Event):
        """Запрос пароля Telegram"""
        password_future = event.data.get('future')
        if password_future:
            # Отправляем событие для показа диалога
            self.event_bus.emit("show_tg_password_dialog", {'future': password_future})
    
    # endregion
    
    # region Обработчики событий - Персонажи
    
    def _on_get_all_characters(self, event: Event):
        """Получение списка всех персонажей"""
        if hasattr(self.model, 'get_all_mitas'):
            return self.model.get_all_mitas()
        return []
    
    def _on_get_current_character(self, event: Event):
        """Получение текущего персонажа"""
        if hasattr(self.model, 'current_character'):
            char = self.model.current_character
            return {
                'name': char.name if hasattr(char, 'name') else '',
                'char_id': char.char_id if hasattr(char, 'char_id') else '',
                'is_cartridge': char.is_cartridge if hasattr(char, 'is_cartridge') else False
            }
        return None
    
    def _on_set_character_to_change(self, event: Event):
        """Установка персонажа для изменения"""
        character_name = event.data.get('character')
        if character_name and hasattr(self.model, 'current_character_to_change'):
            self.model.current_character_to_change = character_name
    
    def _on_check_change_character(self, event: Event):
        """Проверка изменения персонажа"""
        if hasattr(self.model, 'check_change_current_character'):
            self.model.check_change_current_character()
    
    def _on_get_character(self, event: Event):
        """Получение персонажа по имени"""
        character_name = event.data.get('name')
        if character_name and hasattr(self.model, 'characters'):
            return self.model.characters.get(character_name)
        return None
    
    def _on_reload_character_data(self, event: Event):
        """Перезагрузка данных персонажа"""
        if hasattr(self.model, 'current_character'):
            char = self.model.current_character
            if hasattr(char, 'reload_character_data'):
                char.reload_character_data()
    
    def _on_reload_character_prompts(self, event: Event):
        """Перезагрузка промптов персонажа"""
        character_name = event.data.get('character')
        if character_name and hasattr(self.model, 'characters'):
            char = self.model.characters.get(character_name)
            if char and hasattr(char, 'reload_prompts'):
                char.reload_prompts()
    
    def _on_clear_character_history(self, event: Event):
        """Очистка истории текущего персонажа"""
        if hasattr(self.model, 'current_character'):
            char = self.model.current_character
            if hasattr(char, 'clear_history'):
                char.clear_history()
    
    def _on_clear_all_histories(self, event: Event):
        """Очистка истории всех персонажей"""
        if hasattr(self.model, 'characters'):
            for character in self.model.characters.values():
                if hasattr(character, 'clear_history'):
                    character.clear_history()
    
    # endregion
    
    # region Обработчики событий - Микрофон
    
    def _on_set_microphone(self, event: Event):
        """Установка микрофона"""
        microphone_name = event.data.get('name')
        device_id = event.data.get('device_id')
        
        if microphone_name and device_id is not None:
            if hasattr(self, 'speech_controller'):
                self.speech_controller.selected_microphone = microphone_name
                self.speech_controller.device_id = device_id
            
            self.selected_microphone = microphone_name
            self.device_id = device_id
            
            # Сохраняем настройки
            self.settings.set("NM_MICROPHONE_ID", device_id)
            self.settings.set("NM_MICROPHONE_NAME", microphone_name)
            self.settings.save_settings()
            
            logger.info(f"Выбран микрофон: {microphone_name} (ID: {device_id})")
    
    def _on_start_speech_recognition(self, event: Event):
        """Запуск распознавания речи"""
        device_id = event.data.get('device_id', 0)
        
        try:
            from handlers.asr_handler import SpeechRecognition
            if hasattr(self, 'loop'):
                SpeechRecognition.speech_recognition_start(device_id, self.loop)
                logger.info("Распознавание речи запущено")
        except Exception as e:
            logger.error(f"Ошибка запуска распознавания речи: {e}")
    
    def _on_stop_speech_recognition(self, event: Event):
        """Остановка распознавания речи"""
        try:
            from handlers.asr_handler import SpeechRecognition
            SpeechRecognition.speech_recognition_stop()
            logger.info("Распознавание речи остановлено")
        except Exception as e:
            logger.error(f"Ошибка остановки распознавания речи: {e}")
    
    def _on_update_speech_settings(self, event: Event):
        """Обновление настроек речи"""
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key and hasattr(self, 'speech_controller'):
            self.speech_controller.update_speech_settings(key, value)
    
    # endregion
    
    # region Обработчики событий - Асинхронные операции
    
    def _on_get_event_loop(self, event: Event):
        """Получение event loop"""
        if hasattr(self, 'loop'):
            return self.loop
        return None
    
    def _on_reload_prompts_async(self, event: Event):
        """Асинхронная перезагрузка промптов"""
        if self.loop and self.loop.is_running():
            import asyncio
            asyncio.run_coroutine_threadsafe(self._async_reload_prompts(), self.loop)
        else:
            logger.error("Цикл событий asyncio не запущен. Невозможно выполнить асинхронную загрузку промптов.")
            self.event_bus.emit("reload_prompts_failed", {"error": "Event loop not running"})
    
    async def _async_reload_prompts(self):
        """Асинхронная загрузка промптов"""
        try:
            from utils.prompt_downloader import PromptDownloader
            downloader = PromptDownloader()
            success = await self.loop.run_in_executor(None, downloader.download_and_replace_prompts)
            
            if success:
                # Получаем персонажа для перезагрузки
                if hasattr(self.model, 'current_character_to_change'):
                    character_name = self.model.current_character_to_change
                    character = self.model.characters.get(character_name)
                    if character:
                        await self.loop.run_in_executor(None, character.reload_prompts)
                    else:
                        logger.error("Персонаж для перезагрузки не найден")
                
                self.event_bus.emit("reload_prompts_success")
            else:
                self.event_bus.emit("reload_prompts_failed", {"error": "Download failed"})
        except Exception as e:
            logger.error(f"Ошибка при обновлении промптов: {e}")
            self.event_bus.emit("reload_prompts_failed", {"error": str(e)})
    
    # endregion
    
    # region Обработчики событий - Загрузка
    
    def _on_show_loading_popup(self, event: Event):
        """Показать попап загрузки"""
        message = event.data.get('message', 'Loading...')
        self.event_bus.emit("display_loading_popup", {"message": message})
    
    def _on_close_loading_popup(self, event: Event):
        """Закрыть попап загрузки"""
        self.event_bus.emit("hide_loading_popup")
    
    # endregion

    # region Обработчики событий - Отладка

    def _on_get_debug_info(self, event: Event):
        """Получение отладочной информации"""
        if hasattr(self.model, 'current_character'):
            char = self.model.current_character
            if hasattr(char, 'current_variables_string'):
                return char.current_variables_string()
        return "Debug info not available"

    # endregion

    # region Обработчики событий - От chat_handler.py

    def _on_set_tts_data(self, event: Event):
        """Установка данных для TTS"""
        data = event.data
        self.textToTalk = data.get('text', '')
        self.textSpeaker = data.get('speaker', '')
        self.textSpeakerMiku = data.get('speaker_miku', '')
        self.silero_turn_off_video = data.get('turn_off_video', True)
        
        logger.info(f"TTS Text: {self.textToTalk}, Speaker: {self.textSpeaker}")

    def _on_get_user_input(self, event: Event):
        """Получение текста из user_entry"""
        return self.gui_controller.get_user_input()
    
    # endregion

    # region Обработчики событий - От server.py

    def _on_update_game_connection(self, event: Event):
        """Обновление статуса подключения к игре"""
        is_connected = event.data.get('is_connected', False)
        self.update_game_connection(is_connected)

    def _on_set_character_to_change_server(self, event: Event):
        """Установка персонажа для изменения от сервера"""
        character = event.data.get('character', '')
        if self.model and hasattr(self.model, 'current_character_to_change'):
            self.model.current_character_to_change = character

    def _on_set_game_data(self, event: Event):
        """Установка игровых данных"""
        if self.model:
            self.model.distance = event.data.get('distance', 0.0)
            self.model.roomPlayer = event.data.get('roomPlayer', -1)
            self.model.roomMita = event.data.get('roomMita', -1)
            self.model.nearObjects = event.data.get('nearObjects', '')
            self.model.actualInfo = event.data.get('actualInfo', '')

    def _on_set_dialog_active(self, event: Event):
        """Установка статуса активного диалога"""
        self.dialog_active = event.data.get('active', False)

    def _on_add_temporary_system_info(self, event: Event):
        """Добавление временной системной информации"""
        content = event.data.get('content', '')
        if content and self.model and hasattr(self.model, 'add_temporary_system_info'):
            self.model.add_temporary_system_info(content)

    def _on_set_id_sound(self, event: Event):
        """Установка ID звука"""
        self.id_sound = event.data.get('id', 0)

    def _on_update_chat(self, event: Event):
        """Обновление чата"""
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

    def _on_get_server_data(self, event: Event):
        """Получение данных сервера"""
        return {
            'patch_to_sound_file': self.patch_to_sound_file,
            'id_sound': self.id_sound,
            'instant_send': self.instant_send,
            'silero_connected': self.silero_connected
        }

    def _on_get_settings(self, event: Event):
        """Получение всех настроек"""
        return self.settings.settings  # Возвращаем весь словарь настроек

    def _on_reset_server_data(self, event: Event):
        """Сброс данных сервера"""
        self.instant_send = False
        self.patch_to_sound_file = ""

    def _on_clear_user_input(self, event: Event):
        """Очистка пользовательского ввода"""
        self.clear_user_input()

    def _on_set_waiting_answer(self, event: Event):
        """Установка статуса ожидания ответа"""
        self.waiting_answer = event.data.get('waiting', False)

    def _on_generate_response(self, event: Event):
        """Генерация ответа через модель"""
        user_input = event.data.get('user_input', '')
        system_input = event.data.get('system_input', '')
        image_data = event.data.get('image_data', [])
        
        if self.model and hasattr(self.model, 'generate_response'):
            return self.model.generate_response(user_input, system_input, image_data)
        return None

    def _on_set_connected_to_game(self, event: Event):
        """Установка статуса подключения к игре"""
        self.ConnectedToGame = event.data.get('connected', False)

    # endregion

    # region Обработчики событий - От telegram_handler.py

    def _on_set_sound_file_data(self, event: Event):
        """Установка данных звукового файла от Telegram"""
        self.patch_to_sound_file = event.data.get('patch_to_sound_file', '')
        self.id_sound = event.data.get('id_sound', 0)
        logger.info(f"Установлены данные звукового файла: {self.patch_to_sound_file}, ID: {self.id_sound}")


    def _on_set_silero_connected(self, event: Event):
        """Установка статуса подключения Silero"""
        self.silero_connected = event.data.get('connected', False)
        logger.info(f"Статус подключения Silero установлен: {self.silero_connected}")

    # endregion
    
    def start_periodic_checks(self):
        """Запуск периодических проверок"""
        # Запускаем проверку текста для озвучки
        import threading
        
        def check_loop():
            while True:
                try:
                    self._on_check_text_to_talk(Event(name="periodic_check"))
                    time.sleep(0.15)
                except Exception as e:
                    logger.error(f"Ошибка в периодической проверке: {e}")
                    time.sleep(1)
        
        thread = threading.Thread(target=check_loop, daemon=True)
        thread.start()

    def _on_send_periodic_image_request(self, event: Event):
        """Обработка периодической отправки изображений"""
        if self.loop and self.loop.is_running():
            import asyncio
            data = event.data
            asyncio.run_coroutine_threadsafe(
                self.async_send_message(
                    user_input=data.get('user_input', ''),
                    system_input=data.get('system_input', ''), 
                    image_data=data.get('image_data', [])
                ),
                self.loop
            )
        else:
            logger.error("Ошибка: Цикл событий не готов для периодической отправки изображений.")

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

    @property  
    def textSpeaker(self):
        return self.audio_controller.textSpeaker

    @textSpeaker.setter
    def textSpeaker(self, value):
        self.audio_controller.textSpeaker = value

    @property
    def textSpeakerMiku(self):
        return self.audio_controller.textSpeakerMiku

    @textSpeakerMiku.setter
    def textSpeakerMiku(self, value):
        self.audio_controller.textSpeakerMiku = value

    @property
    def silero_turn_off_video(self):
        return self.audio_controller.silero_turn_off_video

    @silero_turn_off_video.setter
    def silero_turn_off_video(self, value):
        self.audio_controller.silero_turn_off_video = value