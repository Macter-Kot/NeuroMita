# voice_model_controller.py

import os
import platform
import time
import copy
import json
import threading
from docs import DocsManager
from main_logger import logger
import traceback

from managers.settings_manager import SettingsManager
from utils import getTranslationVariant as _

from ui.windows.voice_model_view import VoiceModelSettingsView, VoiceCollapsibleSection

from PyQt6.QtCore import QTimer

from core.events import get_event_bus, Events

try:
    from utils.gpu_utils import check_gpu_provider, get_cuda_devices, get_gpu_name_by_id
except ImportError:
    logger.info(_("Предупреждение: Модуль GpuUtils не найден. Функции определения GPU не будут работать.", "Warning: GpuUtils module not found. GPU detection functions will not work."))
    def check_gpu_provider(): return None
    def get_cuda_devices(): return []

from core.constants import (model_descriptions, model_descriptions_en, 
                            setting_descriptions, setting_descriptions_en,
                            default_description_text, default_description_text_en)

from core.models_settings import get_default_model_structure

class VoiceModelController:
    def __init__(self, view_parent, config_dir, on_save_callback, local_voice, check_installed_func):
        self.view_parent = view_parent
        self.config_dir = config_dir or os.path.dirname(os.path.abspath(__file__))
        self.settings_values_file = os.path.join(self.config_dir, "voice_model_settings.json")
        self.installed_models_file = os.path.join(self.config_dir, "installed_models.txt")
        self.on_save_callback = on_save_callback
        self.local_voice = local_voice
        self.check_installed_func = check_installed_func

        self.language = SettingsManager.get("LANGUAGE", "RU")
        self.model_descriptions = model_descriptions_en if self.language == "EN" else model_descriptions
        self.setting_descriptions = setting_descriptions_en if self.language == "EN" else setting_descriptions
        self.default_description_text = default_description_text_en if self.language == "EN" else default_description_text

        self.detected_gpu_vendor = check_gpu_provider()
        self.detected_cuda_devices = get_cuda_devices()
        self.gpu_name = None
        if self.detected_cuda_devices:
            first_device_id = self.detected_cuda_devices[0]
            self.gpu_name = get_gpu_name_by_id(first_device_id)

        self.installation_in_progress = False
        self.installed_models = set()
        self.local_voice_models = []

        self.model_components = {
            "low": ["tts_with_rvc"],
            "low+": ["tts_with_rvc"],
            "medium": ["fish_speech_lib"],
            "medium+": ["fish_speech_lib", "triton"],
            "medium+low": ["fish_speech_lib", "triton", "tts_with_rvc"],
            "high": ["f5_tts"],
            "high+low": ["f5_tts", "tts_with_rvc"]
        }

        self.load_installed_models_state()
        self.load_settings()
        
        self.docs_manager = DocsManager()
        self.dependencies_status = self._check_system_dependencies()
        
        self.event_bus = get_event_bus()
        
        # Подписываемся на события запросов данных
        self.event_bus.subscribe(Events.VoiceModel.GET_MODEL_DATA, self._handle_get_model_data, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.GET_INSTALLED_MODELS, self._handle_get_installed_models, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.GET_DEPENDENCIES_STATUS, self._handle_get_dependencies_status, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.GET_DEFAULT_DESCRIPTION, self._handle_get_default_description, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.GET_MODEL_DESCRIPTION, self._handle_get_model_description, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.GET_SETTING_DESCRIPTION, self._handle_get_setting_description, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.GET_SECTION_VALUES, self._handle_get_section_values, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.CHECK_GPU_RTX30_40, self._handle_check_gpu_rtx30_40, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.INSTALL_MODEL, self._handle_install_model, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.UNINSTALL_MODEL, self._handle_uninstall_model, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.SAVE_SETTINGS, self._handle_save_settings, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.CLOSE_DIALOG, self._handle_close_dialog, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.OPEN_DOC, self._handle_open_doc, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.UPDATE_DESCRIPTION, self._handle_update_description, weak=False)
        self.event_bus.subscribe(Events.VoiceModel.CLEAR_DESCRIPTION, self._handle_clear_description, weak=False)
        
        # Создаем View
        self.view = None
        
        
        if view_parent:
            self._create_view()
    
    def _create_view(self):
        """Создает View и добавляет его в родительский виджет"""
        # Удаляем старый View если он есть
        if self.view:
            try:
                if self.view.parent():
                    self.view.setParent(None)
                self.view.deleteLater()
            except:
                pass
            self.view = None
            
        # Создаем новый View
        self.view = VoiceModelSettingsView()
        
        # Если есть родитель, добавляем View в его layout
        if self.view_parent and hasattr(self.view_parent, 'layout'):
            # Очищаем layout перед добавлением
            layout = self.view_parent.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            
            layout.addWidget(self.view)
        
        # Инициализируем данные во View
        self.view._initialize_data()

    def set_view_parent(self, parent):
        """Устанавливает родителя для View и создает View если нужно"""
        self.view_parent = parent
        if not self.view:
            self._create_view()

    def _handle_get_model_data(self, event):
        return self.local_voice_models

    def _handle_get_installed_models(self, event):
        return self.installed_models

    def _handle_get_dependencies_status(self, event):
        status = self.dependencies_status.copy()
        status['detected_gpu_vendor'] = self.detected_gpu_vendor
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
        return self.view.get_section_values(model_id)

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

    def get_default_model_structure(self):
        return get_default_model_structure()
        
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
            if model_id in saved_values:
                model_saved_values = saved_values[model_id]
                if isinstance(model_saved_values, dict):
                    for setting in model_data.get("settings", []):
                        setting_key = setting.get("key")
                        if setting_key in model_saved_values:
                            setting.setdefault("options", {})["default"] = model_saved_values[setting_key]
        self.local_voice_models = merged_model_structure
        
        logger.info(_("Загрузка и адаптация настроек завершена.", "Loading and adaptation of settings completed."))

    def load_installed_models_state(self):
        self.installed_models = set()
        if not self.local_voice or not self.check_installed_func:
            try:
                if os.path.exists(self.installed_models_file):
                    with open(self.installed_models_file, "r", encoding="utf-8") as f:
                        self.installed_models.update(line.strip() for line in f if line.strip())
                    logger.info(f"{_('Загружен список установленных моделей из файла:', 'Loaded list of installed models from file:')} {self.installed_models}") 
            except Exception as e:
                logger.info(f"{_('Ошибка загрузки состояния из', 'Error loading state from')} {self.installed_models_file}: {e}")
        else:
            logger.info(_("Проверка установленных моделей через check_installed_func...", "Checking installed models via check_installed_func..."))
            for model_data in self.get_default_model_structure():
                model_id = model_data.get("id")
                if model_id:
                    # Проверяем напрямую через local_voice для более надежной проверки
                    is_installed = False
                    try:
                        if hasattr(self.local_voice, 'is_model_installed'):
                            is_installed = self.local_voice.is_model_installed(model_id)
                        else:
                            # Fallback на старый метод
                            if model_id == "low": is_installed = self.check_installed_func("tts_with_rvc")
                            elif model_id == "low+": is_installed = self.check_installed_func("tts_with_rvc")
                            elif model_id == "medium": is_installed = self.check_installed_func("fish_speech_lib")
                            elif model_id == "medium+": is_installed = self.check_installed_func("fish_speech_lib") and self.check_installed_func("triton")
                            elif model_id == "medium+low": is_installed = self.check_installed_func("tts_with_rvc") and self.check_installed_func("fish_speech_lib") and self.check_installed_func("triton")
                            elif model_id == "high": is_installed = self.check_installed_func("f5_tts")
                            elif model_id == "high+low": is_installed = self.check_installed_func("f5_tts") and self.check_installed_func("tts_with_rvc")
                    except Exception as e:
                        logger.error(f"Ошибка при проверке установки модели {model_id}: {e}")

                    if is_installed:
                        self.installed_models.add(model_id)
            logger.info(f"{_('Актуальный список установленных моделей:', 'Current list of installed models:')} {self.installed_models}")

    def save_settings(self):
        settings_to_save = {}
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

    def finalize_model_settings(self, models_list, detected_vendor, cuda_devices):
        final_models = copy.deepcopy(models_list)

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
                logger.info(f"{_('Обнаружена GPU', 'Detected GPU')} {self.gpu_name}, {_('принудительно используется FP32 для совместимых настроек.', 'forcing FP32 for compatible settings.')}")
                force_fp32 = True
        elif detected_vendor == "AMD":
            force_fp32 = True

        for model in final_models:
            model_vendors = model.get("gpu_vendor", [])
            vendor_to_adapt_for = None
            if detected_vendor == "NVIDIA" and "NVIDIA" in model_vendors: vendor_to_adapt_for = "NVIDIA"
            elif detected_vendor == "AMD" and "AMD" in model_vendors: vendor_to_adapt_for = "AMD"
            elif not detected_vendor or detected_vendor not in model_vendors: vendor_to_adapt_for = "OTHER"
            elif detected_vendor in model_vendors: vendor_to_adapt_for = detected_vendor

            for setting in model.get("settings", []):
                options = setting.get("options", {})
                setting_key = setting.get("key")
                widget_type = setting.get("type")
                is_device_setting = "device" in str(setting_key).lower()
                is_half_setting = setting_key in ["is_half", "silero_rvc_is_half", "fsprvc_is_half", "half", "fsprvc_fsp_half"]

                final_values_list = None
                adapt_key_suffix = ""
                if vendor_to_adapt_for == "NVIDIA": adapt_key_suffix = "_nvidia"
                elif vendor_to_adapt_for == "AMD": adapt_key_suffix = "_amd"
                elif vendor_to_adapt_for == "OTHER": adapt_key_suffix = "_other"

                values_key = f"values{adapt_key_suffix}"
                default_key = f"default{adapt_key_suffix}"

                if values_key in options: final_values_list = options[values_key]
                elif "values" in options: final_values_list = options["values"]

                if default_key in options: options["default"] = options[default_key]

                if vendor_to_adapt_for == "NVIDIA" and is_device_setting:
                    base_nvidia_values = options.get("values_nvidia", [])
                    base_other_values = options.get("values_other", ["cpu"])
                    base_non_cuda_provider = base_nvidia_values if base_nvidia_values else base_other_values
                    non_cuda_options = [v for v in base_non_cuda_provider if not str(v).startswith("cuda")]
                    if cuda_devices: final_values_list = cuda_devices + non_cuda_options
                    else: final_values_list = [v for v in base_other_values if v in ["cpu", "mps"]] or ["cpu"]

                if final_values_list is not None and widget_type == "combobox":
                    options["values"] = final_values_list

                keys_to_remove = [k for k in options if k.startswith("values_") or k.startswith("default_")]
                for key_to_remove in keys_to_remove: options.pop(key_to_remove, None)

                if force_fp32 and is_half_setting:
                    options["default"] = "False"
                    setting["locked"] = True
                    logger.info(f"  - {_('Принудительно', 'Forcing')} '{setting_key}' = False {_('и заблокировано.', 'and locked.')}")
                elif is_half_setting:
                    logger.info(f"  - '{setting_key}' = True - Доступен.")

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

    def _check_system_dependencies(self):
        """Check system dependencies and return status dict for View"""
        status = {
            'cuda_found': False,
            'winsdk_found': False,
            'msvc_found': False,
            'triton_installed': False,
            'triton_checks_performed': False,
            'show_triton_checks': platform.system() == "Windows"
        }

        if not status['show_triton_checks']:
            logger.info(_("Проверка зависимостей Triton актуальна только для Windows.", "Triton dependency check is relevant only for Windows."))
            return status

        try:
            from triton.windows_utils import find_cuda, find_winsdk, find_msvc
            status['triton_installed'] = True

            cuda_result = find_cuda()
            if isinstance(cuda_result, (tuple, list)) and len(cuda_result) >= 1:
                cuda_path = cuda_result[0]
                status['cuda_found'] = cuda_path is not None and os.path.exists(str(cuda_path)) 
            
            winsdk_result = find_winsdk(False)
            if isinstance(winsdk_result, (tuple, list)) and len(winsdk_result) >= 1:
                winsdk_paths = winsdk_result[0]
                status['winsdk_found'] = isinstance(winsdk_paths, list) and bool(winsdk_paths)
            
            msvc_result = find_msvc(False)
            if isinstance(msvc_result, (tuple, list)) and len(msvc_result) >= 1:
                msvc_paths = msvc_result[0]
                status['msvc_found'] = isinstance(msvc_paths, list) and bool(msvc_paths)

            status['triton_checks_performed'] = True

        except ImportError:
            logger.info(_("Triton не установлен. Невозможно проверить зависимости CUDA/WinSDK/MSVC.", "Triton not installed. Cannot check CUDA/WinSDK/MSVC dependencies."))
            status['triton_installed'] = False
        except Exception as e:
            logger.info(f"{_('Ошибка при проверке зависимостей Triton:', 'Error checking Triton dependencies:')} {e}")

        return status

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

    def handle_install_request(self, model_id, progress_cb=None, status_cb=None, log_cb=None, window=None):
        model_data = next((m for m in self.local_voice_models if m["id"] == model_id), None)
        if not model_data:
            self.view.show_critical(_("Ошибка", "Error"), _("Модель не найдена.", "Model not found."))
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
                f"Эта модель ('{model_name}') оптимизирована для видеокарт NVIDIA RTX 30xx/40xx.\n\n"
                f"Ваша видеокарта ({gpu_info}) может не обеспечить достаточной производительности, "
                "что может привести к медленной работе или нестабильности.\n\n"
                "Продолжить установку?",
                f"This model ('{model_name}') is optimized for NVIDIA RTX 30xx/40xx graphics cards.\n\n"
                f"Your graphics card ({gpu_info}) may not provide sufficient performance, "
                "which could lead to slow operation or instability.\n\n"
                "Continue installation?"
            )
            
            proceed = self.view.show_question(_("Предупреждение", "Warning"), message)

        if proceed:
            self.start_download(model_id, progress_cb, status_cb, log_cb, window)
        elif window:
            QTimer.singleShot(0, window.close)

    def handle_uninstall_request(self, model_id, status_cb=None, log_cb=None, window=None):
        model_name = next((m["name"] for m in self.local_voice_models if m["id"] == model_id), model_id)

        if self.local_voice.is_model_initialized(model_id):
            self.view.show_critical(
                _("Модель Активна", "Model Active"),
                _(f"Модель '{model_name}' сейчас используется или инициализирована.\n\n"
                "Пожалуйста, перезапустите приложение полностью, чтобы освободить ресурсы, "
                "прежде чем удалять эту модель.",
                f"Model '{model_name}' is currently in use or initialized.\n\n"
                "Please restart the application completely to free up resources "
                "before uninstalling this model.")
            )
            if window:
                QTimer.singleShot(0, window.close)
            return

        message = _(f"Вы уверены, что хотите удалить модель '{model_name}'?\n\n"
                    "Будут удалены основной пакет модели и все зависимости, которые больше не используются другими установленными моделями (кроме g4f).\n\n"
                    "Это действие необратимо!",
                    f"Are you sure you want to uninstall the model '{model_name}'?\n\n"
                    "The main model package and all dependencies no longer used by other installed models (except g4f) will be removed.\n\n"
                    "This action is irreversible!")
        
        if self.view.show_question(_("Подтверждение Удаления", "Confirm Uninstallation"), message):
            self.start_uninstall(model_id, status_cb, log_cb, window)
        elif window:
            QTimer.singleShot(0, window.close)

    def start_download(self, model_id, progress_cb=None, status_cb=None, log_cb=None, window=None):
        if self.installation_in_progress:
            return

        self.installation_in_progress = True
        
        self.view.install_started_signal.emit(model_id)
        
        installed_components = set()
        if self.check_installed_func:
            for component in ["tts_with_rvc", "fish_speech_lib", "triton", "f5_tts"]:
                if self.check_installed_func(component):
                    installed_components.add(component)
        
        model_new_components = set(self.model_components.get(model_id, []))
        models_to_mark_installed = self._get_installable_models(model_id, installed_components, model_new_components)
        
        for mid in models_to_mark_installed:
            if mid != model_id:
                QTimer.singleShot(0, lambda m=mid: self.view.set_button_text(m, _("Ожидание...", "Waiting...")))
                QTimer.singleShot(0, lambda m=mid: self.view.set_button_enabled(m, False))
        
        success = False
        try:
            success = self.local_voice.download_model(model_id, progress_cb, status_cb, log_cb)
        except Exception as e:
            logger.exception(f"download_model exception for {model_id}: {e}")
            if log_cb:
                log_cb(f"Ошибка: {str(e)}")
        
        self.handle_download_result(success, model_id, models_to_mark_installed)
        
        self.installation_in_progress = False
        self.view.install_finished_signal.emit({"model_id": model_id, "success": success})
        
        if window and success:
            if status_cb:
                status_cb(_("Установка успешно завершена!", "Installation successful!"))
            QTimer.singleShot(3000, window.close)
        elif window:
            QTimer.singleShot(5000, window.close)

    def _get_installable_models(self, model_id, installed_components, new_components):
        all_components = installed_components | new_components
        installable_models = [model_id]
        
        for mid, required_components in self.model_components.items():
            if mid != model_id and mid not in self.installed_models:
                if all(comp in all_components for comp in required_components):
                    installable_models.append(mid)
        
        return installable_models

    def start_uninstall(self, model_id, status_cb=None, log_cb=None, window=None):
        if self.installation_in_progress:
            return

        self.installation_in_progress = True
        
        # Уведомляем View о начале удаления через сигнал
        self.view.uninstall_started_signal.emit(model_id)

        success = False
        try:
            # Передаем колбэки в local_voice если они есть
            if status_cb or log_cb:
                success = self.local_voice.download_model(model_id, None, status_cb, log_cb)
            else:
                if model_id in ("low", "low+"):
                    success = self.local_voice.uninstall_edge_tts_rvc()
                elif model_id == "medium":
                    success = self.local_voice.uninstall_fish_speech()
                elif model_id in ("medium+", "medium+low"):
                    success = self.local_voice.uninstall_triton_component()
                elif model_id in ("high", "high+low"):
                    success = self.local_voice.uninstall_f5_tts()
                else:
                    logger.error(f"Unknown model_id for uninstall: {model_id}")
                    success = False
        except Exception as e:
            logger.error(f"Uninstall exception for {model_id}: {e}", exc_info=True)
            success = False

        self.handle_uninstall_result(success, model_id)
        
        self.installation_in_progress = False
        self.view.uninstall_finished_signal.emit({"model_id": model_id, "success": success})
        
        if window:
            if success and status_cb:
                status_cb(_("Удаление завершено!", "Uninstallation complete!"))
            QTimer.singleShot(3000 if success else 5000, window.close)

    def handle_download_result(self, success, model_id, models_to_mark_installed):
        if success:
            for mid in models_to_mark_installed:
                if mid not in self.installed_models:
                    self.installed_models.add(mid)
                    logger.info(f"Добавлена модель {mid} в installed_models.")
            
            logger.info(f"{_('Модели', 'Models')} {models_to_mark_installed} {_('помечены как установленные. Перезагрузка настроек...', 'marked as installed. Reloading settings...')}")
            self.load_settings()
            logger.info(_("Настройки перезагружены.", "Settings reloaded."))
            
            self.save_installed_models_list()
            
            if self.on_save_callback:
                callback_data = {
                    "installed_models": list(self.installed_models),
                    "models_data": self.local_voice_models
                }
                self.on_save_callback(callback_data)
            
            logger.info(f"{_('Обработка установки', 'Handling installation of')} {model_id} {_('и связанных моделей завершена.', 'and related models completed.')}")
        else:
            logger.info(f"{_('Ошибка установки модели', 'Error installing model')} {model_id}.")

    def handle_uninstall_result(self, success, model_id):
        model_data = next((m for m in self.local_voice_models if m["id"] == model_id), None)
        model_name = model_data.get("name", model_id) if model_data else model_id

        if success:
            logger.info(f"{_('Удаление модели', 'Uninstallation of model')} {model_id} {_('завершено успешно.', 'completed successfully.')}")
            if model_id in self.installed_models:
                self.installed_models.remove(model_id)
                logger.info(f"Удалена модель {model_id} из installed_models.")

            self.save_installed_models_list()
            
            if self.on_save_callback:
                callback_data = {"installed_models": list(self.installed_models), "models_data": self.local_voice_models}
                self.on_save_callback(callback_data)

        else:
            logger.error(f"{_('Ошибка при удалении модели', 'Error uninstalling model')} {model_id}.")
            self.view.show_critical(_("Ошибка Удаления", "Uninstallation Error"), 
                                    _(f"Не удалось удалить модель '{model_name}'.\nСм. лог для подробностей.", 
                                    f"Could not uninstall model '{model_name}'.\nSee log for details."))

    def save_installed_models_list(self):
        try:
            with open(self.installed_models_file, "w", encoding="utf-8") as f:
                for model_id in sorted(list(self.installed_models)):
                    f.write(f"{model_id}\n")
        except Exception as e:
            logger.info(f"{_('Ошибка сохранения списка установленных моделей в', 'Error saving list of installed models to')} {self.installed_models_file}: {e}")

    def handle_description_update(self, key):
        """Обновляет описание для модели или настройки"""
        if key in self.model_descriptions:
            self.view.update_description_signal.emit(self.model_descriptions[key])
        elif key in self.setting_descriptions:
            self.view.update_description_signal.emit(self.setting_descriptions[key])
        else:
            self.view.update_description_signal.emit(self.default_description_text)

    def handle_clear_description(self):
        self.view.clear_description_signal.emit()

    def save_and_continue(self):
        self.save_settings()

    def save_and_quit(self):
        self.save_settings()
        # Ищем родительский диалог
        if self.view:
            dialog = self.view.window()
            if dialog and hasattr(dialog, 'close'):
                # Используем QTimer чтобы избежать блокировки
                QTimer.singleShot(0, dialog.close)

    def open_doc(self, doc_name):
        self.docs_manager.open_doc(doc_name)