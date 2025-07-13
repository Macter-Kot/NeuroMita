import time
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
import base64

from main_logger import logger
from core.events import get_event_bus, Events, Event


class MainViewLogic:
    """
    Бизнес-логика для MainView.
    Обрабатывает все взаимодействия с контроллером через систему событий.
    """
    
    def __init__(self, controller):
        self.controller = controller
        self.settings = controller.settings
        self.event_bus = get_event_bus()
        
        # Подписываемся на события от View
        self._subscribe_to_events()
        logger.info("MainViewLogic подписался на события")
        
        # Инициализация состояния
        self.model_loading_cancelled = False
    
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
    
    # region Обработчики событий - Сообщения
    
    def _on_send_message(self, event: Event):
        logger.warning("Обработчик события _on_send_message получил сообщение.")
        """Обработка отправки сообщения"""
        data = event.data
        user_input = data.get('user_input', '')
        system_input = data.get('system_input', '')
        image_data = data.get('image_data', [])
        
        # Обновляем время последнего запроса изображения
        if image_data:
            self.controller.last_image_request_time = time.time()
        
        # Отправляем сообщение асинхронно
        
        logger.warning("Проверка на loop")
        if self.controller.loop and self.controller.loop.is_running():
            
            logger.warning("Отправка сообщения асинхронно.")
            asyncio.run_coroutine_threadsafe(
                self.controller.async_send_message(user_input, system_input, image_data),
                self.controller.loop
            )
    
    def _on_clear_chat(self, event: Event):
        """Очистка чата"""
        # Здесь может быть дополнительная логика очистки на стороне контроллера
        pass
    
    def _on_load_history(self, event: Event):
        """Загрузка истории чата"""
        self.controller.loaded_messages_offset = 0
        self.controller.total_messages_in_history = 0
        self.controller.loading_more_history = False
        
        chat_history = self.controller.model.current_character.load_history()
        all_messages = chat_history["messages"]
        self.controller.total_messages_in_history = len(all_messages)
        
        max_display_messages = int(self.settings.get("MAX_CHAT_HISTORY_DISPLAY", 100))
        start_index = max(0, self.controller.total_messages_in_history - max_display_messages)
        messages_to_load = all_messages[start_index:]
        
        self.controller.loaded_messages_offset = len(messages_to_load)
        
        # Отправляем данные обратно во View
        self.event_bus.emit("history_loaded", {
            'messages': messages_to_load,
            'total_messages': self.controller.total_messages_in_history,
            'loaded_offset': self.controller.loaded_messages_offset
        })
    
    def _on_load_more_history(self, event: Event):
        """Загрузка дополнительной истории"""
        if self.controller.loaded_messages_offset >= self.controller.total_messages_in_history:
            return
        
        self.controller.loading_more_history = True
        try:
            chat_history = self.controller.model.current_character.load_history()
            all_messages = chat_history["messages"]
            
            lazy_load_batch_size = getattr(self.controller, 'lazy_load_batch_size', 50)
            end_index = self.controller.total_messages_in_history - self.controller.loaded_messages_offset
            start_index = max(0, end_index - lazy_load_batch_size)
            messages_to_prepend = all_messages[start_index:end_index]
            
            if messages_to_prepend:
                self.controller.loaded_messages_offset += len(messages_to_prepend)
                
                # Отправляем данные обратно во View
                self.event_bus.emit("more_history_loaded", {
                    'messages': messages_to_prepend,
                    'loaded_offset': self.controller.loaded_messages_offset
                })
        finally:
            self.controller.loading_more_history = False
    
    # endregion
    
    # region Обработчики событий - Настройки
    
    def _on_save_setting(self, event: Event):
        """Сохранение настройки"""
        key = event.data.get('key')
        value = event.data.get('value')
        
        if key:
            self.settings.set(key, value)
            self.settings.save_settings()
            self.controller.all_settings_actions(key, value)
    
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
                self.controller.stage_image_bytes(image_data)
            elif isinstance(image_data, str):
                self.controller.staged_images.append(image_data)
    
    def _on_clear_staged_images(self, event: Event):
        """Очистка очереди изображений"""
        self.controller.clear_staged_images()
    
    def _on_capture_screen(self, event: Event):
        """Захват экрана"""
        history_limit = event.data.get('limit', 1) if event.data else 1
        
        if hasattr(self.controller, 'screen_capture_instance'):
            frames = self.controller.screen_capture_instance.get_recent_frames(history_limit)
            return frames
        return []
    
    def _on_get_camera_frames(self, event: Event):
        """Получение кадров с камеры"""
        history_limit = event.data.get('limit', 1) if event.data else 1
        
        if (hasattr(self.controller, 'camera_capture') and 
            self.controller.camera_capture is not None and 
            self.controller.camera_capture.is_running()):
            frames = self.controller.camera_capture.get_recent_frames(history_limit)
            return frames
        return []
    
    # endregion
    
    # region Обработчики событий - Голосовые модели
    
    def _on_select_voice_model(self, event: Event):
        """Выбор голосовой модели"""
        model_id = event.data.get('model_id')
        if model_id and hasattr(self.controller, 'local_voice'):
            try:
                self.controller.local_voice.select_model(model_id)
                self.settings.set("NM_CURRENT_VOICEOVER", model_id)
                self.settings.save_settings()
                self.controller.current_local_voice_id = model_id
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
            success = self.controller.local_voice.init_model(model_id)
            
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
        if model_id and hasattr(self.controller, 'local_voice'):
            return self.controller.local_voice.is_model_installed(model_id)
        return False
    
    def _on_check_model_initialized(self, event: Event):
        """Проверка инициализирована ли модель"""
        model_id = event.data.get('model_id')
        if model_id and hasattr(self.controller, 'local_voice'):
            return self.controller.local_voice.is_model_initialized(model_id)
        return False
    
    def _on_change_voice_language(self, event: Event):
        """Изменение языка озвучки"""
        language = event.data.get('language')
        if language and hasattr(self.controller.local_voice, 'change_voice_language'):
            try:
                self.controller.local_voice.change_voice_language(language)
                return True
            except Exception as e:
                logger.error(f"Ошибка при изменении языка озвучки: {e}")
                return False
        return False
    
    def _on_refresh_voice_modules(self, event: Event):
        """Обновление голосовых модулей"""
        if hasattr(self.controller, 'refresh_local_voice_modules'):
            self.controller.refresh_local_voice_modules()
    
    # endregion
    
    # region Обработчики событий - Статусы
    
    def _on_get_connection_status(self, event: Event):
        """Получение статуса подключения к игре"""
        return self.controller.ConnectedToGame
    
    def _on_get_silero_status(self, event: Event):
        """Получение статуса Silero"""
        return self.controller.silero_connected
    
    def _on_get_mic_status(self, event: Event):
        """Получение статуса микрофона"""
        return self.controller.mic_recognition_active
    
    def _on_get_screen_capture_status(self, event: Event):
        """Получение статуса захвата экрана"""
        return self.controller.screen_capture_active
    
    def _on_get_camera_capture_status(self, event: Event):
        """Получение статуса захвата камеры"""
        return self.controller.camera_capture_active
    
    # endregion
    
    # region Обработчики событий - Управление
    
    def _on_stop_screen_capture(self, event: Event):
        """Остановка захвата экрана"""
        self.controller.stop_screen_capture_thread()
    
    def _on_stop_camera_capture(self, event: Event):
        """Остановка захвата камеры"""
        self.controller.stop_camera_capture_thread()
    
    def _on_delete_sound_files(self, event: Event):
        """Удаление звуковых файлов"""
        self.controller.delete_all_sound_files()
    
    def _on_stop_server(self, event: Event):
        """Остановка сервера"""
        self.controller.stop_server()
    
    # endregion
    
    # region Обработчики событий - Проверки
    
    def _on_check_text_to_talk(self, event: Event):
        """Проверка текста для озвучки"""
        self.controller.check_text_to_talk_or_send()
    
    def _on_get_character_name(self, event: Event):
        """Получение имени персонажа"""
        return self.controller.model.current_character.name
    
    def _on_get_current_context_tokens(self, event: Event):
        """Получение количества токенов текущего контекста"""
        if hasattr(self.controller.model, 'get_current_context_token_count'):
            return self.controller.model.get_current_context_token_count()
        return 0
    
    def _on_calculate_cost(self, event: Event):
        """Расчет стоимости"""
        # Обновляем параметры модели из настроек
        self.controller.model.token_cost_input = float(self.settings.get("TOKEN_COST_INPUT", 0.000001))
        self.controller.model.token_cost_output = float(self.settings.get("TOKEN_COST_OUTPUT", 0.000002))
        self.controller.model.max_model_tokens = int(self.settings.get("MAX_MODEL_TOKENS", 32000))
        
        if hasattr(self.controller.model, 'calculate_cost_for_current_context'):
            return self.controller.model.calculate_cost_for_current_context()
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

    # region Обработчики событий - Персонажи
    
    def _on_get_all_characters(self, event: Event):
        """Получение списка всех персонажей"""
        if hasattr(self.controller.model, 'get_all_mitas'):
            return self.controller.model.get_all_mitas()
        return []
    
    def _on_get_current_character(self, event: Event):
        """Получение текущего персонажа"""
        if hasattr(self.controller.model, 'current_character'):
            char = self.controller.model.current_character
            return {
                'name': char.name if hasattr(char, 'name') else '',
                'char_id': char.char_id if hasattr(char, 'char_id') else '',
                'is_cartridge': char.is_cartridge if hasattr(char, 'is_cartridge') else False
            }
        return None
    
    def _on_set_character_to_change(self, event: Event):
        """Установка персонажа для изменения"""
        character_name = event.data.get('character')
        if character_name and hasattr(self.controller.model, 'current_character_to_change'):
            self.controller.model.current_character_to_change = character_name
    
    def _on_check_change_character(self, event: Event):
        """Проверка изменения персонажа"""
        if hasattr(self.controller.model, 'check_change_current_character'):
            self.controller.model.check_change_current_character()
    
    def _on_get_character(self, event: Event):
        """Получение персонажа по имени"""
        character_name = event.data.get('name')
        if character_name and hasattr(self.controller.model, 'characters'):
            return self.controller.model.characters.get(character_name)
        return None
    
    def _on_reload_character_data(self, event: Event):
        """Перезагрузка данных персонажа"""
        if hasattr(self.controller.model, 'current_character'):
            char = self.controller.model.current_character
            if hasattr(char, 'reload_character_data'):
                char.reload_character_data()
    
    def _on_reload_character_prompts(self, event: Event):
        """Перезагрузка промптов персонажа"""
        character_name = event.data.get('character')
        if character_name and hasattr(self.controller.model, 'characters'):
            char = self.controller.model.characters.get(character_name)
            if char and hasattr(char, 'reload_prompts'):
                char.reload_prompts()
    
    def _on_clear_character_history(self, event: Event):
        """Очистка истории текущего персонажа"""
        if hasattr(self.controller.model, 'current_character'):
            char = self.controller.model.current_character
            if hasattr(char, 'clear_history'):
                char.clear_history()
    
    def _on_clear_all_histories(self, event: Event):
        """Очистка истории всех персонажей"""
        if hasattr(self.controller.model, 'characters'):
            for character in self.controller.model.characters.values():
                if hasattr(character, 'clear_history'):
                    character.clear_history()
    
    # endregion
    
    # region Обработчики событий - Микрофон
    
    def _on_set_microphone(self, event: Event):
        """Установка микрофона"""
        microphone_name = event.data.get('name')
        device_id = event.data.get('device_id')
        
        if microphone_name and device_id is not None:
            if hasattr(self.controller, 'speech_controller'):
                self.controller.speech_controller.selected_microphone = microphone_name
                self.controller.speech_controller.device_id = device_id
            
            self.controller.selected_microphone = microphone_name
            self.controller.device_id = device_id
            
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
            if hasattr(self.controller, 'loop'):
                SpeechRecognition.speech_recognition_start(device_id, self.controller.loop)
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
        
        if key and hasattr(self.controller, 'speech_controller'):
            self.controller.speech_controller.update_speech_settings(key, value)
    
    # endregion
    
    # region Обработчики событий - Асинхронные операции
    
    def _on_get_event_loop(self, event: Event):
        """Получение event loop"""
        if hasattr(self.controller, 'loop'):
            return self.controller.loop
        return None
    
    def _on_reload_prompts_async(self, event: Event):
        """Асинхронная перезагрузка промптов"""
        if self.controller.loop and self.controller.loop.is_running():
            import asyncio
            asyncio.run_coroutine_threadsafe(self._async_reload_prompts(), self.controller.loop)
        else:
            logger.error("Цикл событий asyncio не запущен. Невозможно выполнить асинхронную загрузку промптов.")
            self.event_bus.emit("reload_prompts_failed", {"error": "Event loop not running"})
    
    async def _async_reload_prompts(self):
        """Асинхронная загрузка промптов"""
        try:
            from utils.prompt_downloader import PromptDownloader
            downloader = PromptDownloader()
            success = await self.controller.loop.run_in_executor(None, downloader.download_and_replace_prompts)
            
            if success:
                # Получаем персонажа для перезагрузки
                if hasattr(self.controller.model, 'current_character_to_change'):
                    character_name = self.controller.model.current_character_to_change
                    character = self.controller.model.characters.get(character_name)
                    if character:
                        await self.controller.loop.run_in_executor(None, character.reload_prompts)
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
        if hasattr(self.controller.model, 'current_character'):
            char = self.controller.model.current_character
            if hasattr(char, 'current_variables_string'):
                return char.current_variables_string()
        return "Debug info not available"

    # endregion