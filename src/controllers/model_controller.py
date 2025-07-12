from handlers.chat_handler import ChatModel
from main_logger import logger
import importlib
import sys
import os
import functools
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox
from utils import _

class ModelController:
    def __init__(self, main_controller, api_key, api_key_res, api_url, api_model, makeRequest, pip_installer):
        self.main = main_controller
        self.model = ChatModel(self.main, api_key, api_key_res, api_url, api_model, makeRequest, pip_installer)
        
    def update_model_settings(self, key, value):
        if key == "CHARACTER":
            self.model.current_character_to_change = value
            self.model.check_change_current_character()
        elif key == "NM_API_MODEL":
            self.model.api_model = value.strip()
        elif key == "NM_API_KEY":
            self.model.api_key = value.strip()
        elif key == "NM_API_URL":
            self.model.api_url = value.strip()
        elif key == "NM_API_REQ":
            self.model.makeRequest = bool(value)
        elif key == "gpt4free_model":
            self.model.gpt4free_model = value.strip()
        elif key == "MODEL_MAX_RESPONSE_TOKENS":
            self.model.max_response_tokens = int(value)
        elif key == "MODEL_TEMPERATURE":
            self.model.temperature = float(value)
        elif key == "MODEL_PRESENCE_PENALTY":
            self.model.presence_penalty = float(value)
        elif key == "MODEL_FREQUENCY_PENALTY":
            self.model.frequency_penalty = float(value)
        elif key == "MODEL_LOG_PROBABILITY":
            self.model.log_probability = float(value)
        elif key == "MODEL_TOP_K":
            self.model.top_k = int(value)
        elif key == "MODEL_TOP_P":
            self.model.top_p = float(value)
        elif key == "MODEL_THOUGHT_PROCESS":
            self.model.thinking_budget = float(value)
        elif key == "MODEL_MESSAGE_LIMIT":
            self.model.memory_limit = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_COUNT":
            self.model.max_request_attempts = int(value)
        elif key == "MODEL_MESSAGE_ATTEMPTS_TIME":
            self.model.request_delay = float(value)
        elif key == "IMAGE_QUALITY_REDUCTION_ENABLED":
            self.model.image_quality_reduction_enabled = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_START_INDEX":
            self.model.image_quality_reduction_start_index = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_USE_PERCENTAGE":
            self.model.image_quality_reduction_use_percentage = bool(value)
        elif key == "IMAGE_QUALITY_REDUCTION_MIN_QUALITY":
            self.model.image_quality_reduction_min_quality = int(value)
        elif key == "IMAGE_QUALITY_REDUCTION_DECREASE_RATE":
            self.model.image_quality_reduction_decrease_rate = int(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_ON_LIMIT":
            self.model.enable_history_compression_on_limit = bool(value)
        elif key == "ENABLE_HISTORY_COMPRESSION_PERIODIC":
            self.model.enable_history_compression_periodic = bool(value)
        elif key == "HISTORY_COMPRESSION_OUTPUT_TARGET":
            self.model.history_compression_output_target = str(value)
        elif key == "HISTORY_COMPRESSION_PERIODIC_INTERVAL":
            self.model.history_compression_periodic_interval = int(value)
        elif key == "HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS":
            self.model.history_compression_min_messages_to_compress = float(value)
            
    def init_model_thread(self, model_id, loading_window, status_label, progress):
        try:
            QTimer.singleShot(0, lambda: status_label.setText(_("Загрузка настроек...", "Loading settings...")))

            success = False
            if not self.main.audio_controller.model_loading_cancelled:
                QTimer.singleShot(0, lambda: status_label.setText(_("Инициализация модели...", "Initializing model...")))
                success = self.main.audio_controller.local_voice.initialize_model(model_id, init=True)

            if success and not self.main.audio_controller.model_loading_cancelled:
                QTimer.singleShot(0, functools.partial(self.main.view.finish_model_loading, model_id, loading_window))
            elif not self.main.audio_controller.model_loading_cancelled:
                error_message = _("Не удалось инициализировать модель. Проверьте логи.",
                                  "Failed to initialize model. Check logs.")
                QTimer.singleShot(0, lambda: [
                    status_label.setText(_("Ошибка инициализации!", "Initialization Error!")),
                    progress.setRange(0, 1),
                    QMessageBox.critical(loading_window, _("Ошибка инициализации", "Initialization Error"), error_message),
                    self.main.view.cancel_model_loading(loading_window)
                ])
        except Exception as e:
            logger.error(f"Критическая ошибка в потоке инициализации модели {model_id}: {e}", exc_info=True)
            if not self.main.audio_controller.model_loading_cancelled:
                error_message = _("Критическая ошибка при инициализации модели: ",
                                  "Critical error during model initialization: ") + str(e)
                QTimer.singleShot(0, lambda: [
                    status_label.setText(_("Ошибка!", "Error!")),
                    progress.setRange(0, 1),
                    QMessageBox.critical(loading_window, _("Ошибка", "Error"), error_message),
                    self.main.view.cancel_model_loading(loading_window)
                ])
                
    def refresh_local_voice_modules(self):
        import importlib
        import sys
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
                        self.main.audio_controller.local_voice.tts_rvc_module = actual_class
                    elif module_name == "fish_speech_lib.inference":
                        self.main.audio_controller.local_voice.fish_speech_module = actual_class

                logger.info(f"Модуль {module_name} успешно обработан.")
            except ImportError:
                logger.warning(f"Модуль {module_name} не найден или не установлен.")
                if module_name == "tts_with_rvc":
                    self.main.audio_controller.local_voice.tts_rvc_module = None
                elif module_name == "fish_speech_lib.inference":
                    self.main.audio_controller.local_voice.fish_speech_module = None
            except Exception as e:
                logger.error(f"Ошибка при обработке модуля {module_name}: {e}", exc_info=True)

        self.main.view.check_triton_dependencies()
        
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