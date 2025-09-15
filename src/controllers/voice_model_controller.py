# File: src/controllers/voice_model_controller.py
import os
import platform
import time
import copy
import json
from docs import DocsManager
from main_logger import logger

from managers.settings_manager import SettingsManager
from utils import getTranslationVariant as _

from ui.windows.voice_model_view import VoiceModelSettingsView

from PyQt6.QtCore import QTimer, QEventLoop

from core.events import get_event_bus, Events

try:
    from utils.gpu_utils import check_gpu_provider, get_cuda_devices, get_gpu_name_by_id
except ImportError:
    logger.info(_("Предупреждение: Модуль GpuUtils не найден. Функции определения GPU не будут работать.", "Warning: GpuUtils module not found. GPU detection functions will not work."))
    def check_gpu_provider(): return None
    def get_cuda_devices(): return []


class VoiceModelController:
    """
    GUI-контроллер окна настроек локальных моделей.
    Доменные операции выполняет LocalVoiceController через EventBus.
    """
    def __init__(self, view_parent, config_dir, on_save_callback, local_voice, check_installed_func):
        self.view_parent = view_parent
        self.config_dir = config_dir or os.path.dirname(os.path.abspath(__file__))
        self.settings_values_file = os.path.join(self.config_dir, "voice_model_settings.json")
        self.installed_models_file = os.path.join(self.config_dir, "installed_models.txt")
        self.on_save_callback = on_save_callback

        self._dependencies_status_cache = None
        self._dependencies_status_ts = 0.0

        self._check_installed_func = check_installed_func

        self.language = SettingsManager.get("LANGUAGE", "RU")

        # Новые локальные словари описаний (собираем из моделей)
        self.model_descriptions: dict[str, str] = {}
        self.setting_descriptions: dict[str, str] = {}
        self.default_description_text = _("Наведите курсор на элемент интерфейса для получения описания.",
                                          "Hover over an interface element to get a description.")

        self.detected_gpu_vendor = check_gpu_provider()
        self.detected_cuda_devices = get_cuda_devices()
        self.gpu_name = None
        if self.detected_cuda_devices:
            try:
                from utils.gpu_utils import get_gpu_name_by_id
                self.gpu_name = get_gpu_name_by_id(self.detected_cuda_devices[0])
            except Exception:
                self.gpu_name = None

        self.installation_in_progress = False
        self.installed_models = set()
        self.local_voice_models = []

        # Описания связей компонентов (для UI)
        self.model_components = {
            "low": ["tts_with_rvc"],
            "low+": ["tts_with_rvc"],
            "medium": ["fish_speech_lib"],
            "medium+": ["fish_speech_lib", "triton"],
            "medium+low": ["fish_speech_lib", "triton", "tts_with_rvc"],
            "high": ["f5_tts"],
            "high+low": ["f5_tts", "tts_with_rvc"]
        }

        self.docs_manager = DocsManager()
        self.event_bus = get_event_bus()

        # Первичная загрузка
        self.load_installed_models_state()
        self.load_settings()

        # Подписки на VoiceModel.* (нужны для работы view)
        self._subscribe_to_events()

        self.view = None
        if view_parent:
            self._create_view()

    def _subscribe_to_events(self):
        eb = self.event_bus
        eb.subscribe(Events.VoiceModel.GET_MODEL_DATA, self._handle_get_model_data, weak=False)
        eb.subscribe(Events.VoiceModel.GET_INSTALLED_MODELS, self._handle_get_installed_models, weak=False)
        eb.subscribe(Events.VoiceModel.GET_DEPENDENCIES_STATUS, self._handle_get_dependencies_status, weak=False)
        eb.subscribe(Events.VoiceModel.GET_DEFAULT_DESCRIPTION, self._handle_get_default_description, weak=False)
        eb.subscribe(Events.VoiceModel.GET_MODEL_DESCRIPTION, self._handle_get_model_description, weak=False)
        eb.subscribe(Events.VoiceModel.GET_SETTING_DESCRIPTION, self._handle_get_setting_description, weak=False)
        eb.subscribe(Events.VoiceModel.GET_SECTION_VALUES, self._handle_get_section_values, weak=False)
        eb.subscribe(Events.VoiceModel.CHECK_GPU_RTX30_40, self._handle_check_gpu_rtx30_40, weak=False)
        eb.subscribe(Events.VoiceModel.INSTALL_MODEL, self._handle_install_model, weak=False)
        eb.subscribe(Events.VoiceModel.UNINSTALL_MODEL, self._handle_uninstall_model, weak=False)
        eb.subscribe(Events.VoiceModel.SAVE_SETTINGS, self._handle_save_settings, weak=False)
        eb.subscribe(Events.VoiceModel.CLOSE_DIALOG, self._handle_close_dialog, weak=False)
        eb.subscribe(Events.VoiceModel.OPEN_DOC, self._handle_open_doc, weak=False)
        eb.subscribe(Events.VoiceModel.UPDATE_DESCRIPTION, self._handle_update_description, weak=False)
        eb.subscribe(Events.VoiceModel.CLEAR_DESCRIPTION, self._handle_clear_description, weak=False)

    def _create_view(self):
        if self.view:
            try:
                if self.view.parent():
                    self.view.setParent(None)
                self.view.deleteLater()
            except:
                pass
            self.view = None

        self.view = VoiceModelSettingsView()

        if self.view_parent and hasattr(self.view_parent, 'layout'):
            layout = self.view_parent.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            layout.addWidget(self.view)

        try:
            QTimer.singleShot(0, self.view._initialize_data)
        except Exception:
            pass

    # ---------- Сбор описаний из конфигов моделей ----------

    def _collect_descriptions_from_models(self, models: list[dict]):
        """
        Берём описания ТОЛЬКО из исходных конфигов:
        - описание модели: поле 'description' (или 'desc');
        - описание настройки: поле 'help' (или 'description'/'desc') под её точным key.
        Никакой нормализации ключей, никаких фолбэков.
        """
        self.model_descriptions.clear()
        self.setting_descriptions.clear()

        for m in models or []:
            mid = m.get("id")
            if mid:
                # описание модели
                desc = m.get("description") or m.get("desc")
                if isinstance(desc, str) and desc.strip():
                    self.model_descriptions[mid] = desc.strip()

            # описания настроек — только из того, что есть в конфиге
            for s in (m.get("settings") or []):
                if not isinstance(s, dict):
                    continue
                key = s.get("key")
                if not key:
                    continue
                help_text = s.get("help") or s.get("description") or s.get("desc")
                if isinstance(help_text, str) and help_text.strip():
                    self.setting_descriptions[key] = help_text.strip()
    # ---------- VoiceModel event handlers ----------

    def _handle_get_model_data(self, event):
        return self.local_voice_models

    def _handle_get_installed_models(self, event):
        return self.installed_models.copy()

    def _handle_get_dependencies_status(self, event):
        if self._dependencies_status_cache and (time.time() - self._dependencies_status_ts) < 3.0:
            return self._dependencies_status_cache

        res = self.event_bus.emit_and_wait(Events.Audio.GET_TRITON_STATUS, timeout=2.0)
        status = res[0] if res else {}
        status = status.copy() if isinstance(status, dict) else {}
        status['show_triton_checks'] = (platform.system() == "Windows")
        status['detected_gpu_vendor'] = self.detected_gpu_vendor

        self._dependencies_status_cache = status
        self._dependencies_status_ts = time.time()
        return status

    def _handle_get_default_description(self, event):
        return self.default_description_text

    def _handle_get_model_description(self, event):
        model_id = event.data
        return self.model_descriptions.get(model_id, self.default_description_text)

    def _handle_get_setting_description(self, event):
        setting_key = event.data
        return self.setting_descriptions.get(setting_key, self.default_description_text)

    def _handle_get_section_values(self, event):
        model_id = event.data
        if self.view:
            return self.view.get_section_values(model_id)
        return {}

    def _handle_check_gpu_rtx30_40(self, event):
        return self.is_gpu_rtx30_or_40()

    def _handle_install_model(self, event):
        data = event.data
        model_id = data.get('model_id') if isinstance(data, dict) else data
        progress_cb = data.get('progress_callback') if isinstance(data, dict) else None
        status_cb = data.get('status_callback') if isinstance(data, dict) else None
        log_cb = data.get('log_callback') if isinstance(data, dict) else None
        window = data.get('window') if isinstance(data, dict) else None
        self.handle_install_request(model_id, progress_cb, status_cb, log_cb, window)

    def _handle_uninstall_model(self, event):
        data = event.data
        model_id = data.get('model_id') if isinstance(data, dict) else data
        status_cb = data.get('status_callback') if isinstance(data, dict) else None
        log_cb = data.get('log_callback') if isinstance(data, dict) else None
        window = data.get('window') if isinstance(data, dict) else None
        self.handle_uninstall_request(model_id, status_cb, log_cb, window)

    def _handle_save_settings(self, event):
        self.save_and_continue()

    def _handle_close_dialog(self, event):
        self.save_and_quit()

    def _handle_open_doc(self, event):
        doc_name = event.data
        self.open_doc(doc_name)

    def _handle_update_description(self, event):
        key = event.data
        self.handle_description_update(key)

    def _handle_clear_description(self, event):
        self.handle_clear_description()

    # ---------- Данные и состояние ----------

    def get_default_model_structure(self):
        try:
            res = self.event_bus.emit_and_wait(Events.Audio.GET_ALL_LOCAL_MODEL_CONFIGS, timeout=2.0)
            if res and isinstance(res[0], list):
                return res[0]
        except Exception:
            pass
        try:
            from core.models_settings import get_default_model_structure
            return get_default_model_structure()
        except Exception:
            return []

    def load_settings(self):
        default_model_structure = self.get_default_model_structure()
        adapted_default_structure = self.finalize_model_settings(
            default_model_structure, self.detected_gpu_vendor, self.detected_cuda_devices
        )
        saved_values = {}
        try:
            if os.path.exists(self.settings_values_file):
                with open(self.settings_values_file, "r", encoding="utf-8") as f:
                    saved_values = json.load(f)
        except Exception as e:
            logger.info(f"{_('Ошибка загрузки сохраненных значений из', 'Error loading saved values from')} {self.settings_values_file}: {e}")
            saved_values = {}

        merged_model_structure = copy.deepcopy(adapted_default_structure)
        for model_data in merged_model_structure:
            model_id = model_data.get("id")

            # подмешиваем сохранённые значения
            if model_id in saved_values:
                model_saved_values = saved_values[model_id]
                if isinstance(model_saved_values, dict):
                    for setting in model_data.get("settings", []):
                        setting_key = setting.get("key")
                        if setting_key in model_saved_values:
                            setting.setdefault("options", {})["default"] = model_saved_values[setting_key]

            # безопасные дефолты (для UI)
            model_data.setdefault("languages", [])
            model_data.setdefault("intents", [])     # NEW: для отображения «интентов»
            model_data.setdefault("min_ram", None)
            model_data.setdefault("rec_ram", None)
            model_data.setdefault("cpu", None)
            model_data.setdefault("os", [])
            if not isinstance(model_data.get("gpu_vendor"), (list, tuple)):
                model_data["gpu_vendor"] = [v for v in [model_data.get("gpu_vendor")] if v]

        # Собираем словари описаний из моделей (вместо core/constants.py)
        self._collect_descriptions_from_models(merged_model_structure)

        self.local_voice_models = merged_model_structure
        logger.info(_("Загрузка и адаптация настроек завершена.", "Loading and adaptation of settings completed."))

    def load_installed_models_state(self):
        self.installed_models = set()
        logger.info(_("Проверка установленных моделей через LocalVoiceController...", "Checking installed models via LocalVoiceController..."))
        for model_data in self.get_default_model_structure():
            model_id = model_data.get("id")
            if not model_id:
                continue
            try:
                res = self.event_bus.emit_and_wait(Events.Audio.CHECK_MODEL_INSTALLED, {'model_id': model_id}, timeout=1.0)
                if res and res[0]:
                    self.installed_models.add(model_id)
            except Exception as e:
                logger.error(f"Ошибка при проверке установки модели {model_id}: {e}")
        logger.info(f"{_('Актуальный список установленных моделей:', 'Current list of installed models:')} {self.installed_models}")

    def save_settings(self):
        settings_to_save = {}
        if not self.view:
            return
        all_section_values = self.view.get_all_section_values()
        for model_id in self.installed_models:
            values = all_section_values.get(model_id, {})
            if values:
                settings_to_save[model_id] = values
        if settings_to_save:
            try:
                with open(self.settings_values_file, "w", encoding="utf-8") as f:
                    json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.info(f"{_('Ошибка сохранения значений настроек в', 'Error saving settings values to')} {self.settings_values_file}: {e}")

        if self.on_save_callback:
            callback_data = {
                 "installed_models": list(self.installed_models),
                 "models_data": self.local_voice_models
            }
            self.on_save_callback(callback_data)

    # ---------- Логика адаптации под GPU (UI нужды) ----------

    def finalize_model_settings(self, models_list, detected_vendor, cuda_devices):
        import copy as _copy
        final_models = _copy.deepcopy(models_list)

        gpu_name_upper = self.gpu_name.upper() if self.gpu_name else ""
        force_fp32 = False
        if detected_vendor == "NVIDIA" and gpu_name_upper:
            if (
                ("16" in gpu_name_upper and "V100" not in gpu_name_upper)
                or "P40" in gpu_name_upper
                or "P10" in gpu_name_upper
                or "1060" in gpu_name_upper
                or "1070" in gpu_name_upper
                or "1080" in gpu_name_upper
            ):
                logger.info(_("Обнаружена GPU", "Detected GPU") + f" {self.gpu_name}, " +
                            _("принудительно используется FP32 для совместимых настроек.", "forcing FP32 for compatible settings."))
                force_fp32 = True
        elif detected_vendor == "AMD":
            force_fp32 = True

        for model in final_models:
            model_vendors = model.get("gpu_vendor", [])
            vendor_to_adapt_for = None
            if detected_vendor == "NVIDIA" and "NVIDIA" in model_vendors:
                vendor_to_adapt_for = "NVIDIA"
            elif detected_vendor == "AMD" and "AMD" in model_vendors:
                vendor_to_adapt_for = "AMD"
            elif not detected_vendor or detected_vendor not in model_vendors:
                vendor_to_adapt_for = "OTHER"
            elif detected_vendor in model_vendors:
                vendor_to_adapt_for = detected_vendor

            for setting in model.get("settings", []):
                options = setting.get("options", {})
                setting_key = setting.get("key")
                widget_type = setting.get("type")
                is_device_setting = "device" in str(setting_key).lower()
                is_half_setting = setting_key in ["is_half", "silero_rvc_is_half", "fsprvc_is_half", "half", "fsprvc_fsp_half"]

                final_values_list = None
                adapt_key_suffix = ""
                if vendor_to_adapt_for == "NVIDIA":
                    adapt_key_suffix = "_nvidia"
                elif vendor_to_adapt_for == "AMD":
                    adapt_key_suffix = "_amd"
                elif vendor_to_adapt_for == "OTHER":
                    adapt_key_suffix = "_other"

                values_key = f"values{adapt_key_suffix}"
                default_key = f"default{adapt_key_suffix}"

                if values_key in options:
                    final_values_list = options[values_key]
                elif "values" in options:
                    final_values_list = options["values"]

                if default_key in options:
                    options["default"] = options[default_key]

                if is_device_setting:
                    if vendor_to_adapt_for == "NVIDIA":
                        base_nvidia_values = options.get("values_nvidia", [])
                        base_other_values = options.get("values_other", ["cpu"])
                        base_non_cuda_provider = base_nvidia_values if base_nvidia_values else base_other_values
                        non_cuda_options = [v for v in base_non_cuda_provider if not str(v).startswith("cuda")]
                        if cuda_devices:
                            final_values_list = list(cuda_devices) + non_cuda_options
                        else:
                            final_values_list = [v for v in base_other_values if v in ["cpu", "mps"]] or ["cpu"]
                    else:
                        # macOS: добавим mps если его нет
                        if platform.system() == "Darwin":
                            base_values = final_values_list or options.get("values_other", options.get("values", [])) or ["cpu"]
                            if "mps" not in base_values:
                                base_values = list(base_values) + ["mps"]
                            final_values_list = base_values

                if final_values_list is not None and widget_type == "combobox":
                    options["values"] = final_values_list

                keys_to_remove = [k for k in list(options.keys()) if k.startswith("values_") or k.startswith("default_")]
                for key_to_remove in keys_to_remove:
                    options.pop(key_to_remove, None)

                if force_fp32 and is_half_setting:
                    options["default"] = "False"
                    setting["locked"] = True
                    logger.info("  - " + _("Принудительно", "Forcing") + f" '{setting_key}' = False " + _("и заблокировано.", "and locked."))
                elif is_half_setting:
                    logger.info(f"  - '{setting_key}' = True - " + _("Доступен.", "Available."))

                if widget_type == "combobox" and "default" in options and "values" in options:
                    current_values = options["values"]
                    if isinstance(current_values, list):
                        current_default = options["default"]
                        str_values = [str(v) for v in current_values]
                        str_default = str(current_default)
                        if str_default not in str_values:
                            options["default"] = str_values[0] if str_values else ""
                    else:
                        options["default"] = ""

        return final_models

    def is_gpu_rtx30_or_40(self):
        force_unsupported_str = os.environ.get("RTX_FORCE_UNSUPPORTED", "0")
        force_unsupported = force_unsupported_str.lower() in ['true', '1', 't', 'y', 'yes']

        if force_unsupported:
            logger.info(_("INFO: RTX_FORCE_UNSUPPORTED=1 - Имитация неподходящей GPU для RTX 30+.", "INFO: RTX_FORCE_UNSUPPORTED=1 - Simulating unsuitable GPU for RTX 30+."))
            return False

        if self.detected_gpu_vendor != "NVIDIA" or not self.gpu_name:
            return False

        name_upper = self.gpu_name.upper()
        if "RTX" in name_upper:
            if any(f" {gen}" in name_upper or name_upper.endswith(gen) or f"-{gen}" in name_upper for gen in ["3050", "3060", "3070", "3080", "3090"]):
                return True
            if any(f" {gen}" in name_upper or name_upper.endswith(gen) or f"-{gen}" in name_upper for gen in ["4050", "4060", "4070", "4080", "4090"]):
                return True
        return False

    # ---------- Действия из окна (установка/удаление, сохранение) ----------

    def handle_install_request(self, model_id, progress_cb=None, status_cb=None, log_cb=None, window=None):
        model_data = next((m for m in self.local_voice_models if m["id"] == model_id), None)
        if not model_data:
            self.event_bus.emit(
                Events.GUI.SHOW_ERROR_MESSAGE,
                {
                    "title": _("Ошибка", "Error"),
                    "message": _("Модель не найдена.", "Model not found.")
                }
            )
            if window:
                QTimer.singleShot(0, window.close)
            return

        requires_rtx30plus = model_data.get("rtx30plus", False)
        proceed = True

        if requires_rtx30plus and not self.is_gpu_rtx30_or_40():
            gpu_info = self.gpu_name if self.gpu_name else "не определена"
            if self.detected_gpu_vendor and self.detected_gpu_vendor != "NVIDIA":
                gpu_info = f"{self.detected_gpu_vendor} GPU"

            model_name = model_data.get("name", model_id)
            message = _(
                f"Эта модель ('{model_name}') оптимизирована для NVIDIA RTX 30xx/40xx.\n\n"
                f"Ваша видеокарта ({gpu_info}) может не обеспечить достаточной производительности.\n\n"
                "Продолжить установку?",
                f"This model ('{model_name}') is optimized for NVIDIA RTX 30xx/40xx.\n\n"
                f"Your GPU ({gpu_info}) may be insufficient.\n\n"
                "Continue installation?"
            )

            proceed = self.view.show_question(_("Предупреждение", "Warning"), message)

        if proceed:
            self.start_download(model_id, progress_cb, status_cb, log_cb, window)
        elif window:
            QTimer.singleShot(0, window.close)

    def start_download(self, model_id, progress_cb=None, status_cb=None, log_cb=None, window=None):
        if self.installation_in_progress:
            return

        self.installation_in_progress = True
        if self.view:
            self.view.install_started_signal.emit(model_id)

        installed_components = set()
        model_new_components = set(self.model_components.get(model_id, []))
        models_to_mark_installed = self._get_installable_models(
            model_id, installed_components, model_new_components
        )

        for mid in models_to_mark_installed:
            if self.view and mid != model_id:
                QTimer.singleShot(0, lambda m=mid: self.view.set_button_text(m, _("Ожидание...", "Waiting...")))
                QTimer.singleShot(0, lambda m=mid: self.view.set_button_enabled(m, False))

        success = False
        try:
            res = self.event_bus.emit_and_wait(
                Events.Audio.LOCAL_INSTALL_MODEL, {
                    'model_id': model_id,
                    'progress_callback': progress_cb,
                    'status_callback': status_cb,
                    'log_callback': log_cb
                }, timeout=7200000.0
            )
            success = bool(res and res[0])
        except Exception as e:
            logger.exception(f"download_model exception for {model_id}: {e}")
            if log_cb:
                log_cb(f"Ошибка: {str(e)}")

        self.handle_download_result(success, model_id, models_to_mark_installed)

        self.installation_in_progress = False

        if self.view:
            self.view.install_finished_signal.emit({"model_id": model_id, "success": success})

        if window and success:
            if status_cb:
                status_cb(_("Установка успешно завершена!", "Installation successful!"))
            QTimer.singleShot(3000, window.close)
        elif window:
            QTimer.singleShot(5000, window.close)

    def _get_installable_models(self, model_id, installed_components, new_components):
        all_components = set(installed_components) | set(new_components)
        installable_models = [model_id]

        for mid, required_components in self.model_components.items():
            if mid != model_id and mid not in self.installed_models:
                if all(comp in all_components for comp in required_components):
                    installable_models.append(mid)

        return installable_models

    def handle_download_result(self, success, model_id, models_to_mark_installed):
        if success:
            for mid in models_to_mark_installed:
                if mid not in self.installed_models:
                    self.installed_models.add(mid)
                    logger.info(f"Добавлена модель {mid} в installed_models.")

            self.load_settings()
            self.save_installed_models_list()

            if self.on_save_callback:
                callback_data = {
                    "installed_models": list(self.installed_models),
                    "models_data": self.local_voice_models
                }
                self.on_save_callback(callback_data)

            if self.view:
                QTimer.singleShot(0, self.view.refresh_panels_signal.emit)
                QTimer.singleShot(0, self.view.refresh_settings_signal.emit)

            logger.info(f"{_('Обработка установки', 'Handling installation of')} {model_id} {_('и связанных моделей завершена.', 'and related models completed.')}")
        else:
            logger.info(f"{_('Ошибка установки модели', 'Error installing model')} {model_id}.")

    def handle_uninstall_request(self, model_id, status_cb=None, log_cb=None, window=None):
        model_data = next((m for m in self.local_voice_models if m["id"] == model_id), None)
        model_name = model_data.get("name", model_id) if model_data else model_id

        res = self.event_bus.emit_and_wait(Events.Audio.CHECK_MODEL_INITIALIZED, {'model_id': model_id}, timeout=1.0)
        is_initialized = bool(res and res[0])
        if is_initialized and self.view:
            self.view.show_critical(
                _("Модель Активна", "Model Active"),
                _(f"Модель '{model_name}' сейчас используется или инициализирована.\n\n"
                  "Пожалуйста, перезапустите приложение полностью, чтобы освободить ресурсы, "
                  "прежде чем удалять эту модель.",
                  f"Model '{model_name}' is currently in use or initialized.\n\n"
                  "Please restart the application completely to free resources "
                  "before uninstalling this model.")
            )
            return

        message = _(f"Вы уверены, что хотите удалить модель '{model_name}'?\n\n"
                    "Будут удалены основной пакет модели и зависимости, не используемые другими моделями (кроме g4f).\n\n"
                    "Это действие необратимо!",
                    f"Are you sure you want to uninstall the model '{model_name}'?\n\n"
                    "The main model package and dependencies not used by other models (except g4f) will be removed.\n\n"
                    "This action is irreversible!")

        result_holder = {"answer": False}
        loop = QEventLoop()
        if self.view:
            self.view.ask_question_signal.emit(
                _("Подтверждение Удаления", "Confirm Uninstallation"),
                message, result_holder, loop)
            loop.exec()

        if not result_holder["answer"]:
            return

        win_holder = {}
        win_loop = QEventLoop()
        if self.view:
            self.view.create_voice_action_window_signal.emit(
                _(f"Удаление {model_name}", f"Uninstalling {model_name}"),
                _(f"Удаление {model_name}...", f"Uninstalling {model_name}..."),
                win_holder, win_loop)
            win_loop.exec()
        window = win_holder.get("window")
        __, status_cb, log_cb = window.get_threadsafe_callbacks() if window else (None, status_cb, log_cb)
        self.start_uninstall(model_id, status_cb, log_cb, window)

    def start_uninstall(self, model_id, status_cb=None, log_cb=None, window=None):
        if self.installation_in_progress:
            return

        self.installation_in_progress = True
        if self.view:
            self.view.uninstall_started_signal.emit(model_id)

        success = False
        try:
            res = self.event_bus.emit_and_wait(
                Events.Audio.LOCAL_UNINSTALL_MODEL, {
                    'model_id': model_id,
                    'status_callback': status_cb,
                    'log_callback': log_cb
                }, timeout=600.0
            )
            success = bool(res and res[0])
        except Exception as e:
            logger.error(f"Uninstall exception for {model_id}: {e}", exc_info=True)
            success = False

        self.handle_uninstall_result(success, model_id)

        self.installation_in_progress = False
        if self.view:
            self.view.uninstall_finished_signal.emit({"model_id": model_id, "success": success})

        if window:
            if success and status_cb:
                status_cb(_("Удаление завершено!", "Uninstallation complete!"))
            elif status_cb:
                status_cb(_("Удаление завершено с ОШИБКОЙ!", "Uninstallation failed!"))

            QTimer.singleShot(3000 if success else 5000, window.close)

    def handle_uninstall_result(self, success, model_id):
        model_data = next((m for m in self.local_voice_models if m["id"] == model_id), None)
        model_name = model_data.get("name", model_id) if model_data else model_id

        if success:
            prev = self.installed_models.copy()
            self.load_installed_models_state()
            removed = prev - self.installed_models
            if removed:
                logger.info(f"После удаления {model_id} сняты флаги установленных для: {removed}")

            self.save_installed_models_list()

            if self.on_save_callback:
                callback_data = {
                    "installed_models": list(self.installed_models),
                    "models_data": self.local_voice_models
                }
                self.on_save_callback(callback_data)

            if self.view:
                QTimer.singleShot(0, self.view.refresh_panels_signal.emit)
                QTimer.singleShot(0, self.view.refresh_settings_signal.emit)
        else:
            self.event_bus.emit(
                Events.GUI.SHOW_ERROR_MESSAGE,
                {
                    "title": _("Ошибка Удаления", "Uninstallation Error"),
                    "message": _(f"Не удалось удалить модель '{model_name}'.\nСм. лог для подробностей.",
                                f"Could not uninstall model '{model_name}'.\nSee log for details.")
                }
            )

    def save_installed_models_list(self):
        try:
            with open(self.installed_models_file, "w", encoding="utf-8") as f:
                for model_id in sorted(list(self.installed_models)):
                    f.write(f"{model_id}\n")
        except Exception as e:
            logger.info(f"{_('Ошибка сохранения списка установленных моделей в', 'Error saving list of installed models to')} {self.installed_models_file}: {e}")

    # ---------- Вспомогательное ----------

    def handle_description_update(self, key):
        if key in self.model_descriptions and self.view:
            self.view.update_description_signal.emit(self.model_descriptions[key])
        elif key in self.setting_descriptions and self.view:
            self.view.update_description_signal.emit(self.setting_descriptions[key])
        elif self.view:
            self.view.update_description_signal.emit(self.default_description_text)

    def handle_clear_description(self):
        if self.view:
            self.view.clear_description_signal.emit()

    def save_and_continue(self):
        self.save_settings()

    def save_and_quit(self):
        self.save_settings()
        if self.view:
            dialog = self.view.window()
            if dialog and hasattr(dialog, 'close'):
                QTimer.singleShot(0, dialog.close)

    def open_doc(self, doc_name):
        self.docs_manager.open_doc(doc_name)