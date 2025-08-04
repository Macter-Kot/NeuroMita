import io
import uuid
import os
import sys
import importlib
import glob
import asyncio
import functools
from handlers.audio_handler import AudioHandler
from main_logger import logger
from handlers.local_voice_handler import LocalVoice
from ui.settings.voiceover_settings import LOCAL_VOICE_MODELS
from utils import _
from core.events import get_event_bus, Events, Event
from managers.task_manager import TaskStatus

class AudioController:
    def __init__(self, main_controller):
        self.main_controller = main_controller
        self.settings = main_controller.settings
        self.event_bus = get_event_bus()
        self.local_voice = LocalVoice(main_controller)
        self.voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")
        self.current_local_voice_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
        self.last_voice_model_selected = None
        if self.current_local_voice_id:
            for model_info in LOCAL_VOICE_MODELS:
                if model_info["id"] == self.current_local_voice_id:
                    self.last_voice_model_selected = model_info
                    break
        self.model_loading_cancelled = False
        
        self.textSpeaker = "/speaker Mita"
        self.textSpeakerMiku = "/set_person CrazyMita"

        self.id_sound = -1
        self.waiting_answer = False

        self._subscribe_to_events()

    def _subscribe_to_events(self):
        self.event_bus.subscribe(Events.Audio.VOICEOVER_REQUESTED, self._on_voiceover_requested, weak=False)
        self.event_bus.subscribe(Events.Audio.SELECT_VOICE_MODEL, self._on_select_voice_model, weak=False)
        self.event_bus.subscribe(Events.Audio.INIT_VOICE_MODEL, self._on_init_voice_model, weak=False)
        self.event_bus.subscribe(Events.Audio.CHECK_MODEL_INSTALLED, self._on_check_model_installed, weak=False)
        self.event_bus.subscribe(Events.Audio.CHECK_MODEL_INITIALIZED, self._on_check_model_initialized, weak=False)
        self.event_bus.subscribe(Events.Audio.CHANGE_VOICE_LANGUAGE, self._on_change_voice_language, weak=False)
        self.event_bus.subscribe(Events.Audio.REFRESH_VOICE_MODULES, self._on_refresh_voice_modules, weak=False)
        self.event_bus.subscribe(Events.Audio.DELETE_SOUND_FILES, self._on_delete_sound_files, weak=False)
        self.event_bus.subscribe(Events.Audio.GET_WAITING_ANSWER, self._on_get_waiting_answer, weak=False)
        self.event_bus.subscribe(Events.Audio.SET_WAITING_ANSWER, self._on_set_waiting_answer, weak=False)
        self.event_bus.subscribe(Events.Audio.OPEN_VOICE_MODEL_SETTINGS, self._on_open_voice_model_settings, weak=False)
        self.event_bus.subscribe(Events.Audio.GET_TRITON_STATUS, self._on_get_triton_status, weak=False)

    def _on_get_triton_status(self, event: Event):
        if self.local_voice:
            # Если есть метод _check_system_dependencies, вызываем его
            if hasattr(self.local_voice, '_check_system_dependencies'):
                try:
                    self.local_voice._check_system_dependencies()
                except Exception as e:
                    logger.warning(f"Ошибка при проверке зависимостей: {e}")
            return self.local_voice.get_triton_status()
        return {}
        
    def _on_open_voice_model_settings(self, event: Event):
        """
        GUI запрашивает данные для окна «Локальные модели».
        Возвращаем только данные, без создания контроллера.
        """
        try:
            return {
                'local_voice': self.local_voice,
                'config_dir': "Settings",
                'settings': self.settings
            }
        except Exception as e:
            logger.error(f"_on_open_voice_model_settings: {e}", exc_info=True)
            return None

    def _on_voiceover_requested(self, event: Event):
        data = event.data
        text = data.get('text', '')
        speaker = data.get('speaker', self.textSpeaker)
        task_uid = data.get('task_uid')  # Изменено с message_id
        
        if not text:
            return
            
        logger.info(f"Получен запрос на озвучку: {text[:50]}... с task_uid: {task_uid}")
        
        loop = self.event_bus.emit_and_wait(Events.Core.GET_EVENT_LOOP)[0]
        if loop and loop.is_running():
            try:
                self.waiting_answer = True
                self.voiceover_method = self.settings.get("VOICEOVER_METHOD", "TG")

                if self.voiceover_method == "TG":
                    logger.info(f"Используем Telegram (Silero/Miku) для озвучки: {speaker}")
                    self.event_bus.emit(Events.Core.RUN_IN_LOOP, {
                        'coroutine': self.run_send_and_receive(text, speaker, task_uid)
                    })

                elif self.voiceover_method == "Local":
                    selected_local_model_id = self.settings.get("NM_CURRENT_VOICEOVER", None)
                    if selected_local_model_id:
                        logger.info(f"Используем {selected_local_model_id} для локальной озвучки")
                        if self.local_voice.is_model_initialized(selected_local_model_id):
                            self.event_bus.emit(Events.Core.RUN_IN_LOOP, {
                                'coroutine': self.run_local_voiceover(text, task_uid)
                            })
                        else:
                            logger.warning(f"Модель {selected_local_model_id} выбрана, но не инициализирована.")
                            if task_uid:
                                self._update_task_failed_voiceover(task_uid, "Model not initialized")
                    else:
                        logger.warning("Локальная озвучка выбрана, но конкретная модель не установлена/не выбрана.")
                        if task_uid:
                            self._update_task_failed_voiceover(task_uid, "No model selected")
                else:
                    logger.warning(f"Неизвестный метод озвучки: {self.voiceover_method}")
                    if task_uid:
                        self._update_task_failed_voiceover(task_uid, "Unknown voiceover method")

                logger.info("Выполнено")
            except Exception as e:
                logger.error(f"Ошибка при отправке текста на озвучку: {e}")
                if task_uid:
                    self._update_task_failed_voiceover(task_uid, str(e))
            finally:
                self.waiting_answer = False
        else:
            logger.error("Ошибка: Цикл событий не готов.")
            if task_uid:
                self._update_task_failed_voiceover(task_uid, "Event loop not ready")

    def _update_task_failed_voiceover(self, task_uid: str, error: str):
        """Вспомогательный метод для обновления статуса задачи при ошибке озвучки"""
        self.event_bus.emit(Events.Task.UPDATE_TASK_STATUS, {
            'uid': task_uid,
            'status': TaskStatus.FAILED_ON_VOICEOVER,
            'error': error
        })

    def _on_get_waiting_answer(self, event: Event):
        return self.waiting_answer

    
    def _on_select_voice_model(self, event: Event):
        model_id = event.data.get('model_id')
        if model_id and self.local_voice:
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
        model_id = event.data.get('model_id')
        progress_callback = event.data.get('progress_callback')
        
        if model_id:
            # Запускаем асинхронную инициализацию через event loop
            self.event_bus.emit(Events.Core.RUN_IN_LOOP, {
                'coroutine': self._async_init_model(model_id, progress_callback)
            })
    
    async def _async_init_model(self, model_id: str, progress_callback=None):
        """Асинхронная инициализация модели"""
        try:
            if progress_callback:
                progress_callback("status", "Инициализация модели...")
            
            # Получаем event loop
            loop = asyncio.get_running_loop()
            
            # Запускаем синхронную инициализацию в executor
            # Используем правильный метод initialize_model вместо init_model
            success = await loop.run_in_executor(
                None, 
                self.local_voice.initialize_model,  # Исправлено!
                model_id,
                True  # init=True
            )
            
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
        model_id = event.data.get('model_id')
        if model_id and self.local_voice:
            return self.local_voice.is_model_installed(model_id)
        return False
    
    def _on_check_model_initialized(self, event: Event):
        model_id = event.data.get('model_id')
        if model_id and self.local_voice:
            return self.local_voice.is_model_initialized(model_id)
        return False
    
    def _on_change_voice_language(self, event: Event):
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
        self.refresh_local_voice_modules()
    
    def _on_delete_sound_files(self, event: Event):
        self.delete_all_sound_files()
        
    def get_speaker_text(self):
        if self.settings.get("AUDIO_BOT") == "@CrazyMitaAIbot":
            return self.textSpeakerMiku
        else:
            return self.textSpeaker

    async def run_send_and_receive(self, response, speaker_command, task_uid=None):
        logger.info("Попытка получить фразу")
        
        future = asyncio.Future()
        
        self.event_bus.emit(Events.Telegram.TELEGRAM_SEND_VOICE_REQUEST, {
            'text': response,
            'speaker_command': speaker_command,
            'id': 0,  # Для совместимости
            'future': future,
            'task_uid': task_uid
        })
        
        try:
            await future
            result = future.result()
            logger.notify(result)
            voiceover_path = result
            # Успешная озвучка
            if task_uid:
                
                self.event_bus.emit(Events.Task.UPDATE_TASK_STATUS, {
                    'uid': task_uid,
                    'status': TaskStatus.SUCCESS,
                    'result': {
                        'response': response,
                        'voiceover_path': voiceover_path
                    }
                })
        except Exception as e:
            logger.error(f"Ошибка при получении озвучки через Telegram: {e}")
            if task_uid:
                self._update_task_failed_voiceover(task_uid, str(e))
        
        logger.info("Завершение получения фразы")
          
    async def run_local_voiceover(self, text, task_uid=None):
        result_path = None
        try:
            character = self.event_bus.emit_and_wait(Events.Model.GET_CURRENT_CHARACTER)[0]
            
            output_file = f"MitaVoices/output_{uuid.uuid4()}.wav"
            absolute_audio_path = os.path.abspath(output_file)
            os.makedirs(os.path.dirname(absolute_audio_path), exist_ok=True)

            result_path = await self.local_voice.voiceover(
                text=text,
                output_file=absolute_audio_path,
                character=character
            )

            if result_path:
                logger.info(f"Локальная озвучка сохранена в: {result_path}")
                
                # Обновляем статус задачи на SUCCESS
                if task_uid:
                    self.event_bus.emit(Events.Task.UPDATE_TASK_STATUS, {
                        'uid': task_uid,
                        'status': TaskStatus.SUCCESS,
                        'result': {
                            'response': text,
                            'voiceover_path': result_path
                        }
                    })
                
                # Остальная логика для совместимости со старым API
                is_connected = self.event_bus.emit_and_wait(Events.Server.GET_GAME_CONNECTION)[0]
                
                if not is_connected and self.settings.get("VOICEOVER_LOCAL_CHAT"):
                    await AudioHandler.handle_voice_file(result_path, self.settings.get("LOCAL_VOICE_DELETE_AUDIO",
                                                                                        True) if os.environ.get(
                        "ENABLE_VOICE_DELETE_CHECKBOX", "0") == "1" else True)
                elif is_connected:
                    self.event_bus.emit(Events.Server.SET_PATCH_TO_SOUND_FILE, result_path)
                else:
                    logger.info("Озвучка в локальном чате отключена.")
            else:
                logger.error("Локальная озвучка не удалась, файл не создан.")
                if task_uid:
                    self._update_task_failed_voiceover(task_uid, "Failed to create voice file")

        except Exception as e:
            logger.error(f"Ошибка при выполнении локальной озвучки: {e}")
            if task_uid:
                self._update_task_failed_voiceover(task_uid, str(e))

    def refresh_local_voice_modules(self):
        logger.info("Попытка обновления модулей локальной озвучки...")

        modules_to_check = {
            "tts_with_rvc": "TTS_RVC",
            "fish_speech_lib.inference": "FishSpeech",
            "f5_tts": None,
            "triton": None
        }
        
        lib_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Lib")
        if lib_path not in sys.path:
            sys.path.insert(0, lib_path)

        for module_name, class_name in modules_to_check.items():
            try:
                if module_name in sys.modules:
                    logger.debug(f"Перезагрузка модуля: {module_name}")
                    importlib.reload(sys.modules[module_name])
                else:
                    logger.debug(f"Импорт модуля: {module_name}")
                    imported_module = importlib.import_module(module_name)

                if class_name:
                    actual_class = getattr(sys.modules[module_name], class_name)
                    if module_name == "tts_with_rvc":
                        self.local_voice.tts_rvc_module = actual_class
                    elif module_name == "fish_speech_lib.inference":
                        self.local_voice.fish_speech_module = actual_class

                logger.info(f"Модуль {module_name} успешно обработан.")
            except ImportError:
                logger.warning(f"Модуль {module_name} не найден или не установлен.")
                if module_name == "tts_with_rvc":
                    self.local_voice.tts_rvc_module = None
                elif module_name == "fish_speech_lib.inference":
                    self.local_voice.fish_speech_module = None
            except Exception as e:
                logger.error(f"Ошибка при обработке модуля {module_name}: {e}", exc_info=True)

        self.event_bus.emit(Events.GUI.CHECK_TRITON_DEPENDENCIES)

    def init_model_thread(self, model_id, loading_window, status_label, progress):
        """Совместимость со старым API - запускает асинхронную инициализацию через систему событий"""
        try:
            self.event_bus.emit(Events.Audio.UPDATE_MODEL_LOADING_STATUS, {
                'status': _("Загрузка настроек...", "Loading settings...")
            })

            # Создаем callback для обновления статуса
            def progress_callback(status_type, message):
                if status_type == "status":
                    self.event_bus.emit(Events.Audio.UPDATE_MODEL_LOADING_STATUS, {
                        'status': message
                    })

            # Запускаем асинхронную инициализацию через event bus
            self.event_bus.emit(Events.Core.RUN_IN_LOOP, {
                'coroutine': self._async_init_model_with_ui(model_id, progress_callback)
            })
            
        except Exception as e:
            logger.error(f"Критическая ошибка при запуске инициализации модели {model_id}: {e}", exc_info=True)
            if not self.model_loading_cancelled:
                error_message = _("Критическая ошибка при инициализации модели: ",
                                  "Critical error during model initialization: ") + str(e)
                self.event_bus.emit(Events.Audio.UPDATE_MODEL_LOADING_STATUS, {
                    'status': _("Ошибка!", "Error!")
                })
                self.event_bus.emit(Events.GUI.SHOW_ERROR_MESSAGE, {
                    'title': _("Ошибка", "Error"),
                    'message': error_message
                })
                self.event_bus.emit(Events.Audio.CANCEL_MODEL_LOADING)

    async def _async_init_model_with_ui(self, model_id: str, progress_callback):
        """Асинхронная инициализация с обновлением UI"""
        try:
            if not self.model_loading_cancelled:
                self.event_bus.emit(Events.Audio.UPDATE_MODEL_LOADING_STATUS, {
                    'status': _("Инициализация модели...", "Initializing model...")
                })
                
                # Получаем event loop
                loop = asyncio.get_running_loop()
                
                # Запускаем синхронную инициализацию в executor
                success = await loop.run_in_executor(
                    None,
                    self.local_voice.initialize_model,
                    model_id,
                    True  # init=True
                )

            if success and not self.model_loading_cancelled:
                self.event_bus.emit(Events.Audio.FINISH_MODEL_LOADING, {
                    'model_id': model_id
                })
            elif not self.model_loading_cancelled:
                error_message = _("Не удалось инициализировать модель. Проверьте логи.",
                                  "Failed to initialize model. Check logs.")
                self.event_bus.emit(Events.Audio.UPDATE_MODEL_LOADING_STATUS, {
                    'status': _("Ошибка инициализации!", "Initialization Error!")
                })
                self.event_bus.emit(Events.GUI.SHOW_ERROR_MESSAGE, {
                    'title': _("Ошибка инициализации", "Initialization Error"),
                    'message': error_message
                })
                self.event_bus.emit(Events.Audio.CANCEL_MODEL_LOADING)
                
        except Exception as e:
            logger.error(f"Ошибка при инициализации модели с UI {model_id}: {e}", exc_info=True)
            if not self.model_loading_cancelled:
                error_message = _("Критическая ошибка при инициализации модели: ",
                                  "Critical error during model initialization: ") + str(e)
                self.event_bus.emit(Events.Audio.UPDATE_MODEL_LOADING_STATUS, {
                    'status': _("Ошибка!", "Error!")
                })
                self.event_bus.emit(Events.GUI.SHOW_ERROR_MESSAGE, {
                    'title': _("Ошибка", "Error"),
                    'message': error_message
                })
                self.event_bus.emit(Events.Audio.CANCEL_MODEL_LOADING)

    def check_module_installed(self, module_name):
        logger.info(f"Проверка установки модуля: {module_name}")
        spec = None
        try:
            spec = importlib.util.find_spec(module_name)

            if spec is None:
                logger.info(f"Модуль {module_name} НЕ найден через find_spec.")
                return False
            else:
                if spec.loader is not None:
                    try:
                        module = importlib.import_module(module_name)
                        if hasattr(module, '__spec__') and module.__spec__ is not None:
                            logger.info(f"Модуль {module_name} найден (find_spec + loader + import).")
                            return True
                        else:
                            logger.warning(f"Модуль {module_name} импортирован, но __spec__ is None или отсутствует. Считаем не установленным корректно.")
                            if module_name in sys.modules:
                                try:
                                    del sys.modules[module_name]
                                except KeyError:
                                    pass
                            return False
                    except ImportError as ie:
                        logger.warning(f"Модуль {module_name} найден find_spec, но не импортируется: {ie}. Считаем не установленным.")
                        return False
                    except ValueError as ve:
                        logger.warning(f"Модуль {module_name} найден find_spec, но ошибка ValueError при импорте: {ve}. Считаем не установленным.")
                        return False
                    except Exception as e_import:
                        logger.error(f"Неожиданная ошибка при импорте {module_name} после find_spec: {e_import}")
                        return False
                else:
                    logger.warning(f"Модуль {module_name} найден через find_spec, но loader is None. Считаем не установленным корректно.")
                    return False

        except ValueError as e:
            logger.warning(f"Ошибка ValueError при find_spec для {module_name}: {e}. Считаем не установленным корректно.")
            return False
        except Exception as e:
            logger.error(f"Неожиданная ошибка при вызове find_spec для {module_name}: {e}")
            return False
            
    def check_available_vram(self):
        logger.warning("Проверка VRAM не реализована, возвращается фиктивное значение.")
        try:
            return 100
        except Exception as e:
            logger.error(f"Ошибка при попытке проверки VRAM: {e}")
            return 4
            
    @staticmethod
    def delete_all_sound_files():
        for pattern in ["*.wav", "*.mp3"]:
            files = glob.glob(pattern)
            for file in files:
                try:
                    os.remove(file)
                    logger.info(f"Удален файл: {file}")
                except Exception as e:
                    logger.info(f"Ошибка при удалении файла {file}: {e}")

    def _on_set_waiting_answer(self, event: Event):
        self.waiting_answer = event.data.get('waiting', False)