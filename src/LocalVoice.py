# LocalVoice.py
# Файл для установки и управления локальными моделями озвучки.

import importlib
import queue
import threading
import subprocess
import sys
import os
import asyncio
import pygame
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QTextEdit, QFrame, QWidget, QProgressBar, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QTextCursor
import time
import ffmpeg
from utils.GpuUtils import check_gpu_provider

import hashlib
from datetime import datetime
import traceback
import site
import tempfile
import gc
import soundfile as sf
import re
from xml.sax.saxutils import escape
from typing import Dict, Optional, Any

from packaging.utils import canonicalize_name, NormalizedName
from utils.PipInstaller import PipInstaller, DependencyResolver
from SettingsManager import SettingsManager

# --- Новые импорты для модульной структуры ---
from voice_models.base_model import IVoiceModel
from voice_models.edge_tts_rvc_model import EdgeTTS_RVC_Model
from voice_models.fish_speech_model import FishSpeechModel
from voice_models.f5_tts_model import F5TTSModel

from docs import DocsManager
from Logger import logger

def getTranslationVariant(ru_str, en_str=""):
    if en_str and SettingsManager.get("LANGUAGE") == "EN":
        return en_str
    return ru_str

_ = getTranslationVariant

class LocalVoice:
    def __init__(self, parent=None):
        self.parent = parent
        self.settings = parent.settings if parent else SettingsManager()
        
        self.first_compiled: Optional[bool] = None

        self.current_model_id: Optional[str] = None
        self.active_model_instance: Optional[IVoiceModel] = None
        
        # Создаем один экземпляр для всех RVC-моделей
        edge_rvc_handler = EdgeTTS_RVC_Model(self, "edge_rvc_handler")
        
        self.models: Dict[str, IVoiceModel] = {
            "low": edge_rvc_handler,
            "low+": edge_rvc_handler,
            "medium": FishSpeechModel(self, "medium"),
            "medium+": FishSpeechModel(self, "medium+"),
            "medium+low": FishSpeechModel(self, "medium+low"),
            "f5_tts": F5TTSModel(self, "f5_tts"),
        }

        self.pth_path: Optional[str] = None
        self.index_path: Optional[str] = None
        self.clone_voice_folder: str = "Models"
        self.clone_voice_filename: Optional[str] = None
        self.clone_voice_text: Optional[str] = None
        self.current_character_name: str = ""
        self.current_character: Optional[Any] = None

        self.voice_language = self.settings.get("VOICE_LANGUAGE", "ru")
        self.docs_manager = DocsManager()
        self.provider = check_gpu_provider()
        self.amd_test = os.environ.get('TEST_AS_AMD', '').upper() == 'TRUE'
        if self.provider in ["AMD"] or self.amd_test:
            os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

        self.cuda_found = False
        self.winsdk_found = False
        self.msvc_found = False
        self.triton_installed = False
        self.triton_checks_performed = False
        self._dialog_choice = None
        
        self.known_main_packages = ["tts-with-rvc", "fish-speech-lib", "triton-windows", "f5-tts"]
        self.protected_package = "g4f"
        
        if self.is_triton_installed():
            try:
                self._check_system_dependencies()
            except Exception:
                logger.info(_("Triton установлен, но проверка зависимостей не удалась.", "Triton is installed, but dependency check failed."))

    # =========================================================================
    # НОВЫЕ ПУБЛИЧНЫЕ МЕТОДЫ (Упрощенный интерфейс)
    # =========================================================================

    # LocalVoice.py  ── внутри класса LocalVoice
    def download_model(
            self, model_id: str,
            progress_cb=None, status_cb=None, log_cb=None
        ) -> bool:
        logger.info(f"[DEBUG] LocalVoice.download_model('{model_id}') вызван")
        """
        progress_cb(int 0-100), status_cb(str), log_cb(str)
        передаются из GUI-потока; PipInstaller будет их вызывать.
        """
        model = self.models.get(model_id)
        if not model:
            logger.error(f"Unknown model id {model_id}")
            return False

        # сохраняем колбэки для install-методов
        self._external_progress = progress_cb or (lambda *_: None)
        self._external_status   = status_cb   or (lambda *_: None)
        self._external_log      = log_cb      or (lambda *_: None)

        try:
            ok = model.install()
            logger.info(f"[DEBUG] LocalVoice.download_model → install() вернул {ok}")
            if ok:
                self.current_model_id = model_id
            return ok
        finally:
            # очистка, чтобы следующий вызов был «чистым»
            for attr in ("_external_progress", "_external_status", "_external_log"):
                if hasattr(self, attr):
                    delattr(self, attr)

    def initialize_model(self, model_id: str, init: bool = False) -> bool:
        model_to_init = self.models.get(model_id)
        if not model_to_init:
            logger.error(f"Неизвестный идентификатор модели для инициализации: {model_id}")
            return False
        
        if not model_to_init.is_installed():
            logger.error(f"Модель {model_id} не установлена. Пожалуйста, установите ее сначала.")
            return False
        
        # Шаг 1: Устанавливаем ID модели, которую мы СОБИРАЕМСЯ инициализировать.
        # Это дает дочернему классу правильный контекст.
        self.current_model_id = model_id
        logger.info(f"Попытка инициализации и активации модели '{model_id}'...")

        # Шаг 2: Устанавливаем пути по умолчанию ДО инициализации
        is_nvidia = self.provider in ["NVIDIA"]
        model_ext = 'pth' if is_nvidia else 'onnx'
        self.pth_path = os.path.join(self.clone_voice_folder, f"Mila.{model_ext}")
        self.index_path = os.path.join(self.clone_voice_folder, "Mila.index")
        self.clone_voice_filename = os.path.join(self.clone_voice_folder, "Mila.wav")
        self.clone_voice_text = os.path.join(self.clone_voice_folder, "Mila.txt")
        self.current_character_name = "Mila"

        # Шаг 3: Вызываем инициализацию. Дочерний метод теперь достаточно умен,
        # чтобы догрузить/выгрузить компоненты по необходимости.
        success = model_to_init.initialize(init=init)
        
        if not success:
            logger.error(f"Не удалось инициализировать модель '{model_id}'.")
            # Сбрасываем состояние, если что-то пошло не так
            if self.active_model_instance and self.active_model_instance.model_id == model_id:
                self.active_model_instance = None
            self.current_model_id = None
            return False

        # Шаг 4: Если все прошло успешно, устанавливаем модель как активную.
        self.active_model_instance = model_to_init
        logger.info(f"Модель '{model_id}' успешно установлена как активная.")
        
        return True

    async def voiceover(self, text: str, output_file="output.wav", character: Optional[Any] = None) -> Optional[str]:
        if self.active_model_instance is None or not self.active_model_instance.initialized:
            if self.current_model_id:
                logger.warning(f"Активная модель '{self.current_model_id}' не инициализирована. Попытка автоматической инициализации...")
                if not self.initialize_model(self.current_model_id, init=False):
                     raise Exception(f"Не удалось инициализировать модель '{self.current_model_id}'.")
            else:
                 raise ValueError("Модель не выбрана или не инициализирована.")
        if character is not None:
            self.current_character = character
            is_nvidia = self.provider in ["NVIDIA"]
            short_name = str(getattr(character, 'short_name', "Mila"))
            self.current_character_name = short_name
            self.pth_path = os.path.join(self.clone_voice_folder, f"{short_name}.{'pth' if is_nvidia else 'onnx'}")
            self.index_path = os.path.join(self.clone_voice_folder, f"{short_name}.index")
            self.clone_voice_filename = os.path.join(self.clone_voice_folder, f"{short_name}.wav")
            self.clone_voice_text = os.path.join(self.clone_voice_folder, f"{short_name}.txt")
        else:
            self.current_character_name = "Mila"
            self.pth_path = os.path.join(self.clone_voice_folder, "Mila.pth")
            self.index_path = os.path.join(self.clone_voice_folder, "Mila.index")
            self.clone_voice_filename = os.path.join(self.clone_voice_folder, "Mila.wav")
            self.clone_voice_text = os.path.join(self.clone_voice_folder, "Mila.txt")
        return await self.active_model_instance.voiceover(text, character)

    # =========================================================================
    # Методы для управления и проверки состояния
    # =========================================================================
    
    def is_model_installed(self, model_id: str) -> bool:
        model = self.models.get(model_id)
        if model:
            return model.is_installed()
        return False
        
    def is_model_initialized(self, model_id: str) -> bool:
        model = self.models.get(model_id)
        if model:
            # Для Edge/Silero проверяем готовность к конкретному режиму
            if model_id in ["low", "low+"]:
                if not model.initialized or not model.current_tts_rvc:
                    return False
                if model_id == "low+" and not model.current_silero_model:
                    return False
                return True
            return model.initialized
        return False

    def is_triton_installed(self) -> bool:
        """Проверяет, установлен ли Triton."""
        try:
            libs_path_abs = os.path.abspath("Lib")
            if libs_path_abs not in sys.path:
                sys.path.insert(0, libs_path_abs)
            import triton
            self.triton_installed = True
            return True
        except ImportError:
            self.triton_installed = False
            return False

    def change_voice_language(self, new_voice_language: str):
        logger.info(f"Запрос на изменение языка озвучки на '{new_voice_language}'...")
        self.voice_language = new_voice_language
        logger.info(f"Установлен язык озвучки: {self.voice_language}")
        if self.active_model_instance:
            logger.info(f"Сброс состояния активной модели '{self.active_model_instance.model_id}' из-за смены языка.")
            self.active_model_instance.cleanup_state()
            self.active_model_instance = None
        logger.info("Изменение языка завершено.")

    # =========================================================================
    # Методы удаления
    # =========================================================================
    def uninstall_edge_tts_rvc(self):
        return self.models["low"].uninstall()

    def uninstall_fish_speech(self):
        return self.models["medium"].uninstall()

    def uninstall_f5_tts(self):
        return self.models["f5_tts"].uninstall()

    def uninstall_triton_component(self):
        return self._uninstall_component("Triton", "triton-windows")
    
    def _cleanup_after_uninstall(self, removed_package_name: str):
        logger.info(f"Очистка состояния LocalVoice после удаления пакета: {removed_package_name}")
        
        model_to_reset_ids = []
        if removed_package_name == "tts-with-rvc":
            model_to_reset_ids = ["low", "low+", "medium+low"]
        elif removed_package_name == "fish-speech-lib":
            model_to_reset_ids = ["medium", "medium+", "medium+low"]
        elif removed_package_name == "triton-windows":
            model_to_reset_ids = ["medium+", "medium+low"]
            self.triton_installed = False
            self.triton_checks_performed = False
        elif removed_package_name == "f5-tts":
            model_to_reset_ids = ["f5_tts"]
            
        for model_id in model_to_reset_ids:
            if model := self.models.get(model_id):
                model.cleanup_state()
                if self.active_model_instance and self.active_model_instance.model_id == model_id:
                    self.active_model_instance = None
                    self.current_model_id = None
                    logger.info(f"Активная модель '{model_id}' была сброшена.")

        try:
            importlib.invalidate_caches()
            module_name = removed_package_name.replace('-', '_')
            if module_name in sys.modules:
                del sys.modules[module_name]
        except Exception:
            pass

    # =========================================================================
    # ВНУТРЕННИЕ МЕТОДЫ УСТАНОВКИ (вызываются из классов моделей)
    # =========================================================================

    def download_edge_tts_rvc_internal(self):
        gui_elements = None
        try:
            gui_elements = self._create_installation_window(
                title=_("Скачивание Edge-TTS + RVC", "Downloading Edge-TTS + RVC"),
                initial_status=_("Подготовка...", "Preparing...")
            )
            if not gui_elements:
                return False

            progress_window = gui_elements["window"]
            update_progress = gui_elements["update_progress"]
            update_status = gui_elements["update_status"]
            update_log = gui_elements["update_log"]

            installer = PipInstaller(
                script_path=r"libs\python\python.exe",
                libs_path="Lib",
                update_status=update_status,
                update_log=update_log,
                progress_window=progress_window
            )

            update_progress(10)
            update_log(_("Начало установки Edge-TTS + RVC...", "Starting Edge-TTS + RVC installation..."))

            if self.provider in ["NVIDIA"] and not self.is_cuda_available():
                update_status(_("Установка PyTorch с поддержкой CUDA 12.4...", "Installing PyTorch with CUDA 12.4 support..."))
                update_progress(20)
                success = installer.install_package(
                    ["torch==2.6.0", "torchaudio==2.6.0"],
                    description=_("Установка PyTorch с поддержкой CUDA 12.4...", "Installing PyTorch with CUDA 12.4 support..."),
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu124"]
                )

                if not success:
                    update_status(_("Ошибка при установке PyTorch", "Error installing PyTorch"))
                    QTimer.singleShot(5000, progress_window.close)
                    return False
                update_progress(50)
            else:
                update_progress(50) 

            update_status(_("Установка зависимостей...", "Installing dependencies..."))
            success = installer.install_package(
                "omegaconf",
                description=_("Установка omegaconf...", "Installing omegaconf...")
            )
            if not success:
                update_status(_("Ошибка при установке omegaconf", "Error installing omegaconf"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            update_progress(70)

            package_url = None
            desc = ""
            if self.provider in ["NVIDIA"]:
                package_url = "tts_with_rvc"
                desc = _("Установка основной библиотеки tts-with-rvc (NVIDIA)...", "Installing main library tts-with-rvc (NVIDIA)...")
            elif self.provider in ["AMD"]:
                package_url = "tts_with_rvc_onnx[dml]"
                desc = _("Установка основной библиотеки tts-with-rvc (AMD)...", "Installing main library tts-with-rvc (AMD)...")
            else:
                update_log(_(f"Ошибка: не найдена подходящая видеокарта: {self.provider}", f"Error: suitable graphics card not found: {self.provider}"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            success = installer.install_package(package_url, description=desc)

            if not success:
                update_status(_("Ошибка при установке tts-with-rvc", "Error installing tts-with-rvc"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            libs_path_abs = os.path.abspath("Lib")
            update_progress(95)
            update_status(_("Применение патчей...", "Applying patches..."))
            config_path = os.path.join(libs_path_abs, "fairseq", "dataclass", "configs.py")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    patched_source = re.sub(r"metadata=\{(.*?)help:", r'metadata={\1"help":', source)
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(patched_source)
                    update_log(_("Патч успешно применен к configs.py", "Patch successfully applied to configs.py"))
                except Exception as e:
                    update_log(_(f"Ошибка при патче configs.py: {e}", f"Error patching configs.py: {e}"))
            
            update_progress(100)
            update_status(_("Установка успешно завершена!", "Installation successful!"))
            
            self.models['low']._load_module()
            self.models['low+']._load_module()
            
            QTimer.singleShot(3000, progress_window.close)
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке Edge-TTS + RVC: {e}", exc_info=True)
            if gui_elements and gui_elements["window"]:
                gui_elements["window"].close()
            return False

    def download_fish_speech_internal(self):
        gui_elements = None
        try:
            gui_elements = self._create_installation_window(
                title=_("Скачивание Fish Speech", "Downloading Fish Speech"),
                initial_status=_("Подготовка...", "Preparing...")
            )
            if not gui_elements:
                return False

            progress_window = gui_elements["window"]
            update_progress = gui_elements["update_progress"]
            update_status = gui_elements["update_status"]
            update_log = gui_elements["update_log"]
            
            installer = PipInstaller(
                script_path=r"libs\python\python.exe",
                libs_path="Lib",
                update_status=update_status,
                update_log=update_log,
                progress_window=progress_window
            )

            update_progress(10)
            update_log(_("Начало установки Fish Speech...", "Starting Fish Speech installation..."))

            if self.provider in ["NVIDIA"] and not self.is_cuda_available():
                update_status(_("Установка PyTorch с поддержкой CUDA 12.4...", "Installing PyTorch with CUDA 12.4 support..."))
                update_progress(20)
                success = installer.install_package(
                    ["torch==2.6.0", "torchaudio==2.6.0"],
                    description=_("Установка PyTorch с поддержкой CUDA 12.4...", "Installing PyTorch with CUDA 12.4 support..."),
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu124"]
                )
                if not success:
                    update_status(_("Ошибка при установке PyTorch", "Error installing PyTorch"))
                    QTimer.singleShot(5000, progress_window.close)
                    return False
                update_progress(40)
            else:
                 update_progress(40)

            update_status(_("Установка библиотеки Fish Speech...", "Installing Fish Speech library..."))
            force_install_unsupported = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"
            if self.provider in ["NVIDIA"] or force_install_unsupported:
                success = installer.install_package(
                    "fish_speech_lib",
                    description=_("Установка библиотеки Fish Speech...", "Installing Fish Speech library...")
                )
                if not success:
                    update_status(_("Ошибка при установке Fish Speech", "Error installing Fish Speech"))
                    QTimer.singleShot(5000, progress_window.close)
                    return False
                update_progress(80)

                success = installer.install_package(
                    "librosa==0.9.1",
                    description=_("Установка дополнительной библиотеки librosa...", "Installing additional library librosa...")
                )
                if not success:
                    update_log(_("Предупреждение: Fish Speech может работать некорректно без librosa", "Warning: Fish Speech may not work correctly without librosa"))
            else:
                update_log(_(f"Ошибка: не найдена подходящая видеокарта: {self.provider}", f"Error: suitable graphics card not found: {self.provider}"))
                update_status(_("Требуется NVIDIA GPU", "NVIDIA GPU required"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            update_progress(100)
            update_status(_("Установка успешно завершена!", "Installation successful!"))
            
            self.models['medium']._load_module()
            
            QTimer.singleShot(5000, progress_window.close)
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке Fish Speech: {e}", exc_info=True)
            if gui_elements and gui_elements["window"]:
                gui_elements["window"].close()
            return False


    def download_triton_internal(self):
        """
        Устанавливает Triton, применяет патчи, проверяет зависимости
        (с возможностью повторной попытки при ошибке DLL) и инициализирует ядро.
        """
        gui_elements = None
        self.triton_module = False 

        try:
            # Определяем режим работы (с внешними колбэками или со своим окном)
            have_external = hasattr(self, "_external_log")
            if have_external:
                progress_window = None
                update_progress = getattr(self, "_external_progress", lambda *_: None)
                update_status = getattr(self, "_external_status", lambda *_: None)
                update_log = getattr(self, "_external_log", lambda *_: None)
            else:
                gui_elements = self._create_installation_window(
                    title=_("Установка Triton", "Installing Triton"),
                    initial_status=_("Подготовка...", "Preparing...")
                )
                if not gui_elements:
                    logger.error(_("Не удалось создать окно установки Triton.", "Failed to create Triton installation window."))
                    return False

                progress_window = gui_elements["window"]
                update_progress = gui_elements["update_progress"]
                update_status = gui_elements["update_status"]
                update_log = gui_elements["update_log"]

            script_path = r"libs\python\python.exe"
            libs_path = "Lib"
            libs_path_abs = os.path.abspath(libs_path)

            if not os.path.exists(libs_path):
                os.makedirs(libs_path)
                update_log(_(f"Создана директория: {libs_path}", f"Created directory: {libs_path}"))

            if libs_path_abs not in sys.path:
                sys.path.insert(0, libs_path_abs)
                update_log(_(f"Добавлен путь {libs_path_abs} в sys.path", f"Added path {libs_path_abs} to sys.path"))

            update_progress(10)
            update_log(_("Начало установки Triton...", "Starting Triton installation..."))

            update_progress(20)
            update_status(_("Установка библиотеки Triton...", "Installing Triton library..."))
            update_log(_("Установка пакета triton-windows...", "Installing triton-windows package..."))

            installer = PipInstaller(
                script_path=script_path,
                libs_path=libs_path,
                update_status=update_status,
                update_log=update_log,
                progress_window=progress_window,
                update_progress=update_progress if have_external else None
            )
            success = installer.install_package(
                "triton-windows<3.3.0",
                description=_("Установка библиотеки Triton...", "Installing Triton library..."),
                extra_args=["--upgrade"]
            )

            if not success:
                update_status(_("Ошибка при установке Triton", "Error installing Triton"))
                update_log(_("Не удалось установить пакет Triton. Проверьте лог выше.", "Failed to install Triton package. Check the log above."))
                if not have_external and progress_window and progress_window.winfo_exists():
                    QTimer.singleShot(5000, progress_window.close)
                return False

            # --- Патчи ---
            update_progress(50)
            update_status(_("Применение патчей...", "Applying patches..."))
            update_log(_("Применение необходимых патчей для Triton...", "Applying necessary patches for Triton..."))

            # Патч build.py
            update_log(_("Применение патча к build.py...", "Applying patch to build.py..."))
            build_py_path = os.path.join(libs_path_abs, "triton", "runtime", "build.py")
            if os.path.exists(build_py_path):
                try:
                    with open(build_py_path, "r", encoding="utf-8") as f: 
                        source = f.read()
                    
                    # Патч 1: Путь к tcc.exe
                    try:
                        old_line_tcc = f'cc = os.path.join(sysconfig.get_paths()["platlib"], "triton", "runtime", "tcc", "tcc.exe")'
                    except KeyError:
                        old_line_tcc = 'os.path.join(sysconfig.get_paths()["platlib"], "triton", "runtime", "tcc", "tcc.exe")' 
                        update_log("Предупреждение: Не удалось точно определить старую строку tcc в build.py, используется предположение.")

                    new_line_tcc = 'cc = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tcc", "tcc.exe")'
                    
                    # Патч 2: Удаление -fPIC
                    old_line_fpic = 'cc_cmd = [cc, src, "-O3", "-shared", "-fPIC", "-Wno-psabi", "-o", out]'
                    new_line_fpic = 'cc_cmd = [cc, src, "-O3", "-shared", "-Wno-psabi", "-o", out]'

                    patched_source = source
                    applied_patch_tcc = False
                    applied_patch_fpic = False

                    if old_line_tcc in patched_source:
                        patched_source = patched_source.replace(old_line_tcc, new_line_tcc)
                        applied_patch_tcc = True
                    else:
                        update_log(_("Патч (путь tcc.exe) для build.py уже применен или строка не найдена.", "Patch (tcc.exe path) for build.py already applied or line not found."))

                    if old_line_fpic in patched_source:
                        patched_source = patched_source.replace(old_line_fpic, new_line_fpic)
                        applied_patch_fpic = True
                    else:
                        update_log(_("Патч (удаление -fPIC) для build.py уже применен или строка не найдена.", "Patch (removing -fPIC) for build.py already applied or line not found."))

                    if applied_patch_tcc or applied_patch_fpic:
                        with open(build_py_path, "w", encoding="utf-8") as f: 
                            f.write(patched_source)
                        if applied_patch_tcc: 
                            update_log(_("Патч (путь tcc.exe) успешно применен к build.py", "Patch (tcc.exe path) successfully applied to build.py"))
                        if applied_patch_fpic: 
                            update_log(_("Патч (удаление -fPIC) успешно применен к build.py", "Patch (removing -fPIC) successfully applied to build.py"))

                except Exception as e:
                    update_log(_(f"Ошибка при патче build.py: {e}", f"Error patching build.py: {e}"))
                    update_log(traceback.format_exc())
            else:
                update_log(_("Предупреждение: файл build.py не найден, пропускаем патч", "Warning: build.py file not found, skipping patch"))

            # Патч windows_utils.py
            update_progress(60)
            update_log(_("Применение патча к windows_utils.py...", "Applying patch to windows_utils.py..."))
            windows_utils_path = os.path.join(libs_path_abs, "triton", "windows_utils.py")
            if os.path.exists(windows_utils_path):
                try:
                    with open(windows_utils_path, "r", encoding="utf-8") as f: 
                        source = f.read()
                    old_code_win = "output = subprocess.check_output(command, text=True).strip()"
                    new_code_win = "output = subprocess.check_output(\n            command, text=True, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True, stdin=subprocess.DEVNULL, stderr=subprocess.PIPE\n        ).strip()"
                    if old_code_win in source:
                        patched_source = source.replace(old_code_win, new_code_win)
                        with open(windows_utils_path, "w", encoding="utf-8") as f: 
                            f.write(patched_source)
                        update_log(_("Патч успешно применен к windows_utils.py", "Patch successfully applied to windows_utils.py"))
                    else:
                        update_log(_("Патч для windows_utils.py уже применен или строка не найдена.", "Patch for windows_utils.py already applied or line not found."))
                except Exception as e:
                    update_log(_(f"Ошибка при патче windows_utils.py: {e}", f"Error patching windows_utils.py: {e}"))
                    update_log(traceback.format_exc())
            else:
                update_log(_("Предупреждение: файл windows_utils.py не найден, пропускаем патч", "Warning: windows_utils.py file not found, skipping patch"))

            # Патч compiler.py
            update_progress(70)
            update_log(_("Применение патча к compiler.py...", "Applying patch to compiler.py..."))
            compiler_path = os.path.join(libs_path_abs, "triton", "backends", "nvidia", "compiler.py")
            if os.path.exists(compiler_path):
                try:
                    with open(compiler_path, "r", encoding="utf-8") as f: 
                        source = f.read()
                    old_code_comp_line = 'version = subprocess.check_output([_path_to_binary("ptxas")[0], "--version"]).decode("utf-8")'
                    new_code_comp_line = 'version = subprocess.check_output([_path_to_binary("ptxas")[0], "--version"], creationflags=subprocess.CREATE_NO_WINDOW, stderr=subprocess.PIPE, close_fds=True, stdin=subprocess.DEVNULL).decode("utf-8")'
                    if old_code_comp_line in source:
                        patched_source = source.replace(old_code_comp_line, new_code_comp_line)
                        with open(compiler_path, "w", encoding="utf-8") as f: 
                            f.write(patched_source)
                        update_log(_("Патч успешно применен к compiler.py", "Patch successfully applied to compiler.py"))
                    else:
                        update_log(_("Патч для compiler.py уже применен или строка не найдена.", "Patch for compiler.py already applied or line not found."))
                except Exception as e:
                    update_log(_(f"Ошибка при патче compiler.py: {e}", f"Error patching compiler.py: {e}"))
                    update_log(traceback.format_exc())
            else:
                update_log(_("Предупреждение: файл compiler.py не найден, пропускаем патч", "Warning: compiler.py file not found, skipping patch"))

            # Патч cache.py
            update_log(_("Применение патча к cache.py...", "Applying patch to cache.py..."))
            cache_py_path = os.path.join(libs_path_abs, "triton", "runtime", "cache.py")
            if os.path.exists(cache_py_path):
                try:
                    with open(cache_py_path, "r", encoding="utf-8") as f: 
                        source = f.read()
                    old_line = 'temp_dir = os.path.join(self.cache_dir, f"tmp.pid_{pid}_{rnd_id}")'
                    new_line = 'temp_dir = os.path.join(self.cache_dir, f"tmp.pid_{str(pid)[:5]}_{str(rnd_id)[:5]}")'
                    if old_line in source:
                        patched_source = source.replace(old_line, new_line)
                        with open(cache_py_path, "w", encoding="utf-8") as f: 
                            f.write(patched_source)
                        update_log(_("Патч успешно применен к cache.py", "Patch successfully applied to cache.py"))
                    else:
                        update_log(_("Патч для cache.py уже применен или строка не найдена.", "Patch for cache.py already applied or line not found."))
                except Exception as e:
                    update_log(_(f"Ошибка при патче cache.py: {e}", f"Error patching cache.py: {e}"))
                    update_log(traceback.format_exc())
            else:
                update_log(_("Предупреждение: файл cache.py не найден, пропускаем патч", "Warning: cache.py file not found, skipping patch"))

            # --- Проверка зависимостей с возможностью повтора ---
            update_progress(80)
            update_status(_("Проверка системных зависимостей...", "Checking system dependencies..."))
            update_log(_("Проверка наличия Triton, CUDA, Windows SDK, MSVC...", "Checking for Triton, CUDA, Windows SDK, MSVC..."))

            max_retries = 100
            retries_left = max_retries
            check_successful = False

            while retries_left >= 0:
                show_vc_redist_warning = False
                dependencies_check_error = False
                import_error_occurred = False

                # Сбрасываем состояние перед каждой попыткой
                self.triton_installed = False
                self.triton_checks_performed = False
                self.cuda_found = False
                self.winsdk_found = False
                self.msvc_found = False

                # Дебажный флаг (срабатывает только при первой попытке)
                force_dll_error = os.environ.get("TRITON_DLL_ERROR", "0") == "1"
                if force_dll_error and retries_left == max_retries:
                    update_log(_("TRITON_DLL_ERROR=1 установлен. Симуляция ошибки DLL load failed...", "TRITON_DLL_ERROR=1 set. Simulating DLL load failed error..."))
                    show_vc_redist_warning = True
                    import_error_occurred = True
                else:
                    try:
                        importlib.invalidate_caches()
                        if "triton" in sys.modules:
                            try:
                                del sys.modules["triton"]
                                update_log(_("Удален модуль 'triton' из sys.modules перед проверкой.", "Removed 'triton' module from sys.modules before check."))
                            except KeyError:
                                pass

                        # Вызываем проверку
                        self._check_system_dependencies()
                        update_log(_("_check_system_dependencies выполнена успешно.", "_check_system_dependencies executed successfully."))
                        check_successful = True

                    except ImportError as e:
                        error_message = str(e)
                        import_error_occurred = True
                        if error_message.startswith("DLL load failed while importing libtriton"):
                            update_log(_(f"ОШИБКА: Импорт Triton не удался (DLL load failed): {error_message}", f"ERROR: Triton import failed (DLL load failed): {error_message}"))
                            show_vc_redist_warning = True
                        else:
                            update_log(_(f"ОШИБКА: Неожиданная ошибка импорта: {error_message}", f"ERROR: Unexpected import error: {error_message}"))
                            update_log(traceback.format_exc())
                    except Exception as e:
                        update_log(_(f"ОШИБКА: Общая ошибка во время _check_system_dependencies: {e}", f"ERROR: General error during _check_system_dependencies: {e}"))
                        update_log(traceback.format_exc())
                        dependencies_check_error = True

                # Обработка результата попытки
                if show_vc_redist_warning:
                    update_status(_("Ошибка загрузки Triton! Проверьте VC Redist.", "Triton load error! Check VC Redist."))
                    
                    # Для PyQt6 окон
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setWindowModality(Qt.WindowModality.NonModal)
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, False)
                    
                    user_choice = self._show_vc_redist_warning_dialog()
                    
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
                        progress_window.setWindowModality(Qt.WindowModality.ApplicationModal)

                    if user_choice == "retry" and retries_left > 0:
                        update_log(_("Пользователь выбрал повторить попытку импорта Triton...", "User chose to retry Triton import..."))
                        retries_left -= 1
                        check_successful = False
                        continue
                    else:
                        if user_choice == "retry":
                            update_log(_("Достигнут лимит попыток для импорта Triton.", "Retry limit reached for Triton import."))
                        else:
                            update_log(_("Пользователь закрыл окно предупреждения VC Redist, не решая проблему.", "User closed the VC Redist warning window without resolving the issue."))
                        check_successful = False
                        break

            skip_init = False
            user_action_deps = None

            if not check_successful:
                if show_vc_redist_warning:
                    update_log(_("Импорт Triton не удался (возможно, из-за VC Redist), инициализация ядра будет пропущена.", "Triton import failed (possibly due to VC Redist), kernel initialization will be skipped."))
                elif import_error_occurred:
                    update_log(_("Не удалось импортировать Triton, инициализация ядра будет пропущена.", "Failed to import Triton, kernel initialization will be skipped."))
                else:
                    update_log(_("Проверка зависимостей Triton завершилась с ошибкой. Инициализация ядра будет пропущена.", "Triton dependency check finished with an error. Kernel initialization will be skipped."))
                skip_init = True
                self.triton_module = False
            elif self.triton_installed and self.triton_checks_performed:
                self.triton_module = True
                if not (self.cuda_found and self.winsdk_found and self.msvc_found):
                    update_log(_("Обнаружено отсутствие зависимостей (CUDA/WinSDK/MSVC).", "Missing dependencies detected (CUDA/WinSDK/MSVC)."))
                    update_status(_("Требуется внимание: зависимости Triton", "Attention required: Triton dependencies"))
                    
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setWindowModality(Qt.WindowModality.NonModal)
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, False)
                    
                    user_action_deps = self._show_triton_init_warning_dialog()
                    
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
                        progress_window.setWindowModality(Qt.WindowModality.ApplicationModal)
                else:
                    update_log(_("Все зависимости Triton (CUDA, WinSDK, MSVC) найдены.", "All Triton dependencies (CUDA, WinSDK, MSVC) found."))
                    skip_init = False
            else:
                update_log(_("Неожиданное состояние после проверки зависимостей (check_successful=True, но флаги не установлены). Пропуск инициализации ядра.", "Unexpected state after dependency check (check_successful=True, but flags not set). Skipping kernel initialization."))
                skip_init = True
                self.triton_module = False

            # --- Инициализация ядра (init.py) ---
            if not skip_init:
                update_progress(90)
                update_status(_("Инициализация ядра Triton...", "Initializing Triton kernel..."))
                update_log(_("Начало инициализации ядра (запуск init.py)...", "Starting kernel initialization (running init.py)..."))
                try:
                    temp_dir = "temp"
                    if not os.path.exists(temp_dir):
                        os.makedirs(temp_dir)
                        update_log(_(f"Создана директория: {temp_dir}", f"Created directory: {temp_dir}"))

                    update_log(_("Запуск скрипта инициализации...", "Running initialization script..."))
                    init_cmd = [script_path, "init.py"]
                    update_log(_(f"Выполняем: {' '.join(init_cmd)}", f"Executing: {' '.join(init_cmd)}"))
                    
                    try:
                        result = subprocess.run(
                            init_cmd,
                            capture_output=True,
                            text=True,
                            encoding='utf-8',
                            errors='ignore',
                            check=False,
                            creationflags=subprocess.CREATE_NO_WINDOW
                        )
                        
                        if result.stdout:
                            update_log(_("--- Вывод init.py (stdout) ---", "--- init.py Output (stdout) ---"))
                            for line in result.stdout.splitlines():
                                update_log(line)
                            update_log(_("--- Конец вывода init.py (stdout) ---", "--- End of init.py Output (stdout) ---"))
                        
                        if result.stderr:
                            update_log(_("--- Вывод init.py (stderr) ---", "--- init.py Output (stderr) ---"))
                            for line in result.stderr.splitlines():
                                update_log(f"STDERR: {line}")
                            update_log(_("--- Конец вывода init.py (stderr) ---", "--- End of init.py Output (stderr) ---"))

                        update_log(_(f"Скрипт init.py завершился с кодом: {result.returncode}", f"Script init.py finished with code: {result.returncode}"))
                        init_success = (result.returncode == 0)

                    except FileNotFoundError:
                        update_log(_(f"ОШИБКА: Не найден скрипт инициализации init.py или python.exe по пути: {script_path}", f"ERROR: Initialization script init.py or python.exe not found at path: {script_path}"))
                        init_success = False
                    except Exception as sub_e:
                        update_log(_(f"Ошибка при запуске init.py через subprocess.run: {sub_e}", f"Error running init.py via subprocess.run: {sub_e}"))
                        update_log(traceback.format_exc())
                        init_success = False

                    if not init_success:
                        update_status(_("Ошибка при инициализации ядра", "Error during kernel initialization"))
                        update_log(_("Ошибка при запуске init.py. Проверьте лог выше.", "Error running init.py. Check the log above."))
                    else:
                        output_file_path = os.path.join(temp_dir, "inited.wav")
                        if os.path.exists(output_file_path):
                            update_log(_(f"Проверка успешна: файл {output_file_path} создан", f"Check successful: file {output_file_path} created"))
                            update_progress(95)
                            update_status(_("Инициализация ядра успешно завершена!", "Kernel initialization completed successfully!"))
                        else:
                            update_log(_(f"Предупреждение: Файл {output_file_path} не найден после успешного запуска init.py", f"Warning: File {output_file_path} not found after successful run of init.py"))
                            update_status(_("Предупреждение: Файл инициализации не создан", "Warning: Initialization file not created"))
                            update_progress(90)

                except Exception as e:
                    update_log(_(f"Непредвиденная ошибка при инициализации ядра: {str(e)}", f"Unexpected error during kernel initialization: {str(e)}"))
                    update_log(traceback.format_exc())
                    update_status(_("Ошибка инициализации ядра", "Kernel initialization error"))
                    update_progress(85)
            else:
                update_log(_("Инициализация ядра Triton пропущена.", "Triton kernel initialization skipped."))
                update_status(_("Инициализация ядра пропущена", "Kernel initialization skipped"))
                update_progress(95)

            # --- Завершение ---
            update_progress(100)
            final_message = _("Установка Triton завершена.", "Triton installation complete.")
            if not check_successful and show_vc_redist_warning:
                final_message += _(" ВНИМАНИЕ: Ошибка загрузки DLL (VC Redist?)!", " WARNING: DLL load error (VC Redist?)!")
            elif not check_successful:
                final_message += _(" ВНИМАНИЕ: Ошибка при проверке зависимостей!", " WARNING: Error during dependency check!")
            elif skip_init and user_action_deps == "skip":
                final_message += _(" Инициализация ядра пропущена по выбору.", " Kernel initialization skipped by choice.")
            elif skip_init:
                final_message += _(" Инициализация ядра пропущена.", " Kernel initialization skipped.")

            if check_successful and not skip_init and not (self.cuda_found and self.winsdk_found and self.msvc_found):
                missing_deps = [dep for dep, found in [("CUDA", self.cuda_found), ("WinSDK", self.winsdk_found), ("MSVC", self.msvc_found)] if not found]
                final_message += _(f" Внимание: не найдены зависимости ({', '.join(missing_deps)})!", f" Warning: missing dependencies ({', '.join(missing_deps)})!")

            update_status(final_message)
            update_log(final_message)

            # Добавляем финальный совет
            if not check_successful:
                update_log(_("Если модель medium+ не заработает, проверьте лог, зависимости (особенно VC Redist) и документацию.", "If the medium+ model doesn't work, check the log, dependencies (especially VC Redist), and documentation."))
            elif skip_init:
                update_log(_("Если модель medium+ не заработает, возможно, потребуется запустить init_triton.bat вручную.", "If the medium+ model doesn't work, you might need to run init_triton.bat manually."))
            elif not (self.cuda_found and self.winsdk_found and self.msvc_found):
                update_log(_("Если модель medium+ не заработает, проверьте установку недостающих зависимостей (CUDA/WinSDK/MSVC).", "If the medium+ model doesn't work, check the installation of missing dependencies (CUDA/WinSDK/MSVC)."))

            self.triton_installed = True
            if not have_external and progress_window:
                try:
                    if hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        QTimer.singleShot(5000, progress_window.close)
                except Exception:
                    pass

            return True

        except Exception as e:
            logger.error(_(f"Критическая ошибка при установке Triton: {e}", f"Critical error during Triton installation: {e}"))
            logger.error(traceback.format_exc())
            try:
                if gui_elements and gui_elements["window"]:
                    if hasattr(gui_elements["window"], 'isVisible') and gui_elements["window"].isVisible():
                        gui_elements["update_log"](f"{_('КРИТИЧЕСКАЯ ОШИБКА:', 'CRITICAL ERROR:')} {e}\n{traceback.format_exc()}")
                        gui_elements["update_status"](_("Критическая ошибка установки!", "Critical installation error!"))
                        QTimer.singleShot(10000, gui_elements["window"].close)
                elif have_external:
                    update_log(f"{_('КРИТИЧЕСКАЯ ОШИБКА:', 'CRITICAL ERROR:')} {e}\n{traceback.format_exc()}")
                    update_status(_("Критическая ошибка установки!", "Critical installation error!"))
            except Exception as e_inner:
                logger.info(_(f"Ошибка при попытке обновить лог в окне прогресса: {e_inner}", f"Error trying to update log in progress window: {e_inner}"))
            self.triton_module = False
            return False

    #  LocalVoice.py  ── внутри класса LocalVoice
    def download_f5_tts_internal(self):
        """
        Установка F5-TTS.

        •  Если метод вызван в GUI-потоке без внешних колбэков – создаёт своё окно.
        •  Если вызван из воркера и у LocalVoice присутствуют
        _external_progress / _external_status / _external_log –
        окно НЕ создаётся, все сообщения уводятся во внешние колбэки.
        """
        logger.info("[DEBUG] download_f5_tts_internal вошёл")
        # ─────────────────────────────────────────────────────────
        # 1.  Определяем режим работы
        # ─────────────────────────────────────────────────────────
        have_external = hasattr(self, "_external_log")
        if have_external:
            progress_window = None
            update_progress = getattr(self, "_external_progress", lambda *_: None)
            update_status   = getattr(self, "_external_status",   lambda *_: None)
            update_log      = getattr(self, "_external_log",      lambda *_: None)
        else:
            gui = self._create_installation_window(
                title=_("Установка F5-TTS", "Installing F5-TTS"),
                initial_status=_("Подготовка...", "Preparing...")
            )
            if not gui:
                logger.error("Не удалось создать окно установки F5-TTS.")
                return False

            progress_window = gui["window"]
            update_progress = gui["update_progress"]
            update_status   = gui["update_status"]
            update_log      = gui["update_log"]

        # ─────────────────────────────────────────────────────────
        # 2.  Основная логика установки
        # ─────────────────────────────────────────────────────────
        try:
            installer = PipInstaller(
                    script_path=r"libs\python\python.exe",
                    libs_path="Lib",
                    update_status=update_status,
                    update_log=update_log,
                    progress_window=progress_window,
                    update_progress=update_progress        # ← новинка
                )
            logger.info("[DEBUG] PipInstaller создан, запускаем pip install")

            update_progress(5)
            update_log(_("Начало установки F5-TTS...", "Starting F5-TTS installation..."))

            # PyTorch (если надо)
            if self.provider == "NVIDIA" and not self.is_cuda_available():
                update_status(_("Установка PyTorch (cu124)...", "Installing PyTorch (cu124)..."))
                update_progress(10)
                if not installer.install_package(
                    ["torch==2.6.0", "torchaudio==2.6.0"],
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu124"],
                    description="Install PyTorch cu124"
                ):
                    update_status(_("Ошибка PyTorch", "PyTorch error"))
                    return False

            update_progress(25)

            if not installer.install_package(
                ["f5-tts", "google-api-core"],
                description=_("Установка f5-tts...", "Installing f5-tts...")
            ):
                return False

            update_progress(50)

            # Скачиваем веса
            import requests, math, os
            model_dir = os.path.join("checkpoints", "F5-TTS")
            os.makedirs(model_dir, exist_ok=True)

            def dl(url, dest, descr, start_prog, end_prog):
                if os.path.exists(dest): return
                update_status(descr)
                r = requests.get(url, stream=True, timeout=30)
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                done = 0
                with open(dest, "wb") as fh:
                    for chunk in r.iter_content(8192):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done / total
                            prog = start_prog + (end_prog - start_prog) * pct
                            update_progress(math.floor(prog))

            dl(
                "https://huggingface.co/Misha24-10/F5-TTS_RUSSIAN/resolve/main/"
                "F5TTS_v1_Base/model_240000_inference.safetensors?download=true",
                os.path.join(model_dir, "model.safetensors"),
                _("Загрузка весов модели...", "Downloading model weights..."),
                50, 80
            )

            dl(
                "https://huggingface.co/Misha24-10/F5-TTS_RUSSIAN/resolve/main/"
                "F5TTS_v1_Base/vocab.txt?download=true",
                os.path.join(model_dir, "vocab.txt"),
                _("Загрузка vocab.txt...", "Downloading vocab.txt..."),
                80, 90
            )

            update_progress(100)
            update_status(_("Установка F5-TTS завершена.", "F5-TTS installation complete."))
            self.models["f5_tts"]._load_module()
            return True

        except Exception as e:
            logger.error(f"Ошибка установки F5-TTS: {e}", exc_info=True)
            update_log(f"ERROR: {e}")
            return False

        finally:
            # закрываем своё окно, если оно было создано
            if not have_external and progress_window:
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(3000, progress_window.close)

    # =========================================================================
    # Вспомогательные и GUI функции (остаются здесь)
    # =========================================================================
    
    async def apply_rvc_to_file(self, filepath: str, original_model_id: str) -> Optional[str]:
        """Применяет RVC к существующему аудиофайлу. Используется для модели medium+low."""
        rvc_model_handler = self.models.get("low")
        if not rvc_model_handler or not isinstance(rvc_model_handler, EdgeTTS_RVC_Model):
            logger.error("Не найден обработчик RVC для применения к файлу.")
            return None
            
        if not rvc_model_handler.initialized:
            logger.info("Инициализация RVC компонента на лету...")
            # Инициализируем именно 'low', так как это базовый RVC компонент
            if not self.initialize_model("low"):
                 logger.error("Не удалось инициализировать RVC компонент.")
                 return None

        logger.info(f"Вызов RVC для файла: {filepath}")
        # Передаем ID оригинальной модели, чтобы использовать ее настройки
        return await rvc_model_handler._voiceover_edge_tts_rvc(
            text=None, 
            TEST_WITH_DONE_AUDIO=filepath,
            settings_model_id=original_model_id
        )
        
    def is_cuda_available(self):
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def load_model_settings(self, model_id):
        try:
            settings_file = os.path.join("Settings", "voice_model_settings.json")
            if os.path.exists(settings_file):
                with open(settings_file, "r", encoding="utf-8") as f:
                    all_settings = __import__('json').load(f)
                    return all_settings.get(model_id, {})
            return {}
        except Exception as e:
            logger.info(f"Ошибка при загрузке настроек модели {model_id}: {e}")
            return {}

    async def convert_wav_to_stereo(self, input_path, output_path, atempo: float = 1, volume: str = "1.0", pitch=0):
        try:
            if not os.path.exists(input_path):
                logger.info(f"Файл {input_path} не найден при попытке конвертации.")
                return None
            (
                ffmpeg.input(input_path)
                .filter('rubberband', semitones=pitch, pitchq='quality') 
                .filter('atempo', atempo)
                .filter('volume', volume=volume)  
                .output(output_path, format="wav", acodec="pcm_s16le", ar="44100", ac=2)
                .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
            )
            return output_path
        except Exception as e:
            logger.info(f"Ошибка при конвертации WAV в стерео: {e}")
            return None

    def _check_system_dependencies(self):
        """Проверяет наличие CUDA, Windows SDK и MSVC с помощью triton.
        Предполагается, что вызывающий код обработает ImportError при импорте triton."""
        self.cuda_found = False
        self.winsdk_found = False
        self.msvc_found = False
        self.triton_installed = False
        self.triton_checks_performed = False

        libs_path_abs = os.path.abspath("Lib")
        if libs_path_abs not in sys.path:
            sys.path.insert(0, libs_path_abs)
            logger.info(f"Добавлен путь {libs_path_abs} в sys.path для поиска Triton")

        # Попытка импорта (ImportError ловится выше в download_triton)
        import triton
        from triton.windows_utils import find_cuda, find_winsdk, find_msvc

        self.triton_installed = True # Импорт успешен
        logger.info("Triton импортирован успешно внутри _check_system_dependencies.")

        # --- Проверка CUDA, WinSDK, MSVC с обработкой ошибок ---
        try:
            # CUDA
            try:
                cuda_result = find_cuda()
                logger.info(f"CUDA find_cuda() result: {cuda_result}")
                if isinstance(cuda_result, (tuple, list)) and len(cuda_result) >= 1:
                    cuda_path = cuda_result[0]
                    self.cuda_found = cuda_path is not None and os.path.exists(str(cuda_path))
                else: 
                    self.cuda_found = False
            except Exception as e_cuda:
                logger.warning(f"Ошибка при проверке CUDA: {e_cuda}")
                self.cuda_found = False
            logger.info(f"CUDA Check: Found={self.cuda_found}")

            # WinSDK
            try:
                winsdk_result = find_winsdk(False)
                logger.info(f"WinSDK find_winsdk() result: {winsdk_result}")
                if isinstance(winsdk_result, (tuple, list)) and len(winsdk_result) >= 1:
                    winsdk_paths = winsdk_result[0]
                    self.winsdk_found = isinstance(winsdk_paths, list) and bool(winsdk_paths)
                else: 
                    self.winsdk_found = False
            except Exception as e_winsdk:
                logger.warning(f"Ошибка при проверке WinSDK: {e_winsdk}")
                self.winsdk_found = False
            logger.info(f"WinSDK Check: Found={self.winsdk_found}")

            # MSVC
            try:
                msvc_result = find_msvc(False)
                logger.info(f"MSVC find_msvc() result: {msvc_result}")
                if isinstance(msvc_result, (tuple, list)) and len(msvc_result) >= 1:
                    msvc_paths = msvc_result[0]
                    self.msvc_found = isinstance(msvc_paths, list) and bool(msvc_paths)
                else: 
                    self.msvc_found = False
            except Exception as e_msvc:
                logger.warning(f"Ошибка при проверке MSVC: {e_msvc}")
                self.msvc_found = False
            logger.info(f"MSVC Check: Found={self.msvc_found}")

            # Если дошли сюда без общих ошибок, считаем проверки выполненными
            self.triton_checks_performed = True

        except Exception as e:
            logger.error(f"Общая ошибка при выполнении проверок find_* в Triton: {e}")
            logger.error(traceback.format_exc())
            # triton_installed остается True, но проверки не выполнены
            self.triton_checks_performed = False

    def _create_installation_window(self, title, initial_status="Подготовка..."):
        try:
            dialog = QDialog(self.parent if self.parent and hasattr(self.parent, 'isVisible') else None)
            dialog.setWindowTitle(title)
            dialog.setFixedSize(700, 400)
            dialog.setModal(True)
            dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            
            # Применяем стили
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e1e1e;
                }
                QLabel {
                    color: #ffffff;
                }
                QTextEdit {
                    background-color: #101010;
                    color: #cccccc;
                    border: 1px solid #333;
                }
                QProgressBar {
                    border: 1px solid #555;
                    border-radius: 5px;
                    background-color: #555555;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    border-radius: 5px;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            
            # Заголовок
            title_label = QLabel(title)
            title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title_label)
            
            # Статус и прогресс
            info_layout = QHBoxLayout()
            status_label = QLabel(initial_status)
            status_label.setFont(QFont("Segoe UI", 9))
            info_layout.addWidget(status_label, 1)
            
            progress_value_label = QLabel("0%")
            progress_value_label.setFont(QFont("Segoe UI", 9))
            info_layout.addWidget(progress_value_label)
            
            layout.addLayout(info_layout)
            
            # Прогресс-бар
            progress_bar = QProgressBar()
            progress_bar.setRange(0, 100)
            progress_bar.setTextVisible(False)
            layout.addWidget(progress_bar)
            
            # Лог
            log_text = QTextEdit()
            log_text.setReadOnly(True)
            log_text.setFont(QFont("Consolas", 9))
            layout.addWidget(log_text, 1)
            
            # Функции обновления
            def update_progress(value):
                progress_bar.setValue(int(value))
                progress_value_label.setText(f"{int(value)}%")
                QApplication.processEvents()
            
            def update_status(message):
                status_label.setText(message)
                QApplication.processEvents()
            
            def update_log(text):
                log_text.append(text)
                cursor = log_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                log_text.setTextCursor(cursor)
                QApplication.processEvents()
            
            # Центрируем окно
            if self.parent and hasattr(self.parent, 'geometry'):
                parent_rect = self.parent.geometry()
                dialog.move(
                    parent_rect.center().x() - dialog.width() // 2,
                    parent_rect.center().y() - dialog.height() // 2
                )
            
            dialog.show()
            QApplication.processEvents()
            
            return {
                "window": dialog,
                "update_progress": update_progress,
                "update_status": update_status,
                "update_log": update_log
            }
        except Exception as e:
            logger.error(f"Ошибка при создании окна установки: {e}", exc_info=True)
            return None

    def _create_action_window(self, title, initial_status="Подготовка..."):
        try:
            dialog = QDialog(self.parent if self.parent and hasattr(self.parent, 'isVisible') else None)
            dialog.setWindowTitle(title)
            dialog.setFixedSize(700, 400)
            dialog.setModal(True)
            
            dialog.setStyleSheet("""
                QDialog {
                    background-color: #1e1e1e;
                }
                QLabel {
                    color: #ffffff;
                }
                QTextEdit {
                    background-color: #101010;
                    color: #cccccc;
                    border: 1px solid #333;
                }
            """)
            
            layout = QVBoxLayout(dialog)
            
            # Заголовок
            title_label = QLabel(title)
            title_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(title_label)
            
            # Статус
            status_label = QLabel(initial_status)
            status_label.setFont(QFont("Segoe UI", 9))
            layout.addWidget(status_label)
            
            # Лог
            log_text = QTextEdit()
            log_text.setReadOnly(True)
            log_text.setFont(QFont("Consolas", 9))
            layout.addWidget(log_text, 1)
            
            def update_status(message):
                status_label.setText(message)
                QApplication.processEvents()
            
            def update_log(text):
                log_text.append(text)
                cursor = log_text.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                log_text.setTextCursor(cursor)
                QApplication.processEvents()
            
            # Центрируем окно
            if self.parent and hasattr(self.parent, 'geometry'):
                parent_rect = self.parent.geometry()
                dialog.move(
                    parent_rect.center().x() - dialog.width() // 2,
                    parent_rect.center().y() - dialog.height() // 2
                )
            
            dialog.show()
            QApplication.processEvents()
            
            return {
                "window": dialog,
                "update_status": update_status,
                "update_log": update_log
            }
        except Exception as e:
            logger.error(f"Ошибка создания окна действия: {e}")
            traceback.print_exc()
            return None

    def _show_vc_redist_warning_dialog(self):
        """Отображает диалоговое окно с предупреждением об установке VC Redist"""
        dialog = QDialog(self.parent if self.parent and hasattr(self.parent, 'isVisible') else None)
        dialog.setWindowTitle(_("⚠️ Ошибка загрузки Triton", "⚠️ Triton Load Error"))
        dialog.setModal(True)
        dialog.setFixedSize(500, 250)
        
        dialog.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #ffffff; }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #555555; }
            #RetryButton { background-color: #4CAF50; }
            #RetryButton:hover { background-color: #45a049; }
        """)
        
        layout = QVBoxLayout(dialog)
        
        # Заголовок
        title_label = QLabel(_("Ошибка импорта Triton (DLL Load Failed)", "Triton Import Error (DLL Load Failed)"))
        title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        title_label.setStyleSheet("color: orange;")
        layout.addWidget(title_label)
        
        # Текст
        info_text = _(
            "Не удалось загрузить библиотеку для Triton (возможно, отсутствует VC++ Redistributable).\n"
            "Установите последнюю версию VC++ Redistributable (x64) с сайта Microsoft\n"
            "или попробуйте импортировать снова, если вы только что его установили.",
            "Failed to load the library for Triton (VC++ Redistributable might be missing).\n"
            "Install the latest VC++ Redistributable (x64) from the Microsoft website\n"
            "or try importing again if you just installed it."
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        docs_button = QPushButton(_("Документация", "Documentation"))
        docs_button.clicked.connect(lambda: self.docs_manager.open_doc("installation_guide.html#vc_redist"))
        button_layout.addWidget(docs_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton(_("Закрыть", "Close"))
        close_button.clicked.connect(lambda: setattr(self, '_dialog_choice', 'close') or dialog.accept())
        button_layout.addWidget(close_button)
        
        retry_button = QPushButton(_("Попробовать снова", "Retry"))
        retry_button.setObjectName("RetryButton")
        retry_button.clicked.connect(lambda: setattr(self, '_dialog_choice', 'retry') or dialog.accept())
        button_layout.addWidget(retry_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec()
        return self._dialog_choice

    def _show_triton_init_warning_dialog(self):
        """Отображает диалоговое окно с предупреждением о зависимостях Triton."""
        dialog = QDialog(self.parent if self.parent and hasattr(self.parent, 'isVisible') else None)
        dialog.setWindowTitle(_("⚠️ Зависимости Triton", "⚠️ Triton Dependencies"))
        dialog.setModal(True)
        dialog.setFixedSize(600, 350)
        
        dialog.setStyleSheet("""
            QDialog { background-color: #1e1e1e; }
            QLabel { color: #ffffff; }
            QPushButton {
                background-color: #333333;
                color: #ffffff;
                border: none;
                padding: 5px 10px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #555555; }
            #ContinueButton { background-color: #4CAF50; }
            #ContinueButton:hover { background-color: #45a049; }
        """)
        
        layout = QVBoxLayout(dialog)
        
        # Заголовок
        title_label = QLabel(_("Статус зависимостей Triton:", "Triton Dependency Status:"))
        title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(title_label)
        
        # Статусы
        self.status_layout = QHBoxLayout()
        self.status_labels = {}
        self._update_status_display()
        layout.addLayout(self.status_layout)
        
        # Предупреждение
        self.warning_label = QLabel(_("⚠️ Модели Fish Speech+ / + RVC требуют всех компонентов!", 
                                     "⚠️ Models Fish Speech+ / + RVC require all components!"))
        self.warning_label.setStyleSheet("color: orange; font-weight: bold;")
        self.warning_label.setVisible(not (self.cuda_found and self.winsdk_found and self.msvc_found))
        layout.addWidget(self.warning_label)
        
        # Информация
        info_text = _(
            "Если компоненты не найдены, установите их согласно документации.\n"
            "Вы также можете попробовать инициализировать модель вручную,\n"
            "запустив `init_triton.bat` в корневой папке программы.",
            "If components are not found, install them according to the documentation.\n"
            "You can also try initializing the model manually\n"
            "by running `init_triton.bat` in the program's root folder."
        )
        info_label = QLabel(info_text)
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        layout.addStretch()
        
        # Кнопки
        button_layout = QHBoxLayout()
        
        docs_button = QPushButton(_("Открыть документацию", "Open Documentation"))
        docs_button.clicked.connect(lambda: self.docs_manager.open_doc("installation_guide.html"))
        button_layout.addWidget(docs_button)
        
        refresh_button = QPushButton(_("Обновить статус", "Refresh Status"))
        refresh_button.clicked.connect(self._on_refresh_status)
        button_layout.addWidget(refresh_button)
        
        button_layout.addStretch()
        
        skip_button = QPushButton(_("Пропустить инициализацию", "Skip Initialization"))
        skip_button.clicked.connect(lambda: setattr(self, '_dialog_choice', 'skip') or dialog.accept())
        button_layout.addWidget(skip_button)
        
        continue_button = QPushButton(_("Продолжить инициализацию", "Continue Initialization"))
        continue_button.setObjectName("ContinueButton")
        continue_button.clicked.connect(lambda: setattr(self, '_dialog_choice', 'continue') or dialog.accept())
        button_layout.addWidget(continue_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec()
        return self._dialog_choice

    def _update_status_display(self):
        """Обновляет отображение статусов в диалоге"""
        # Очищаем предыдущие виджеты
        while self.status_layout.count():
            item = self.status_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        items = [
            ("CUDA Toolkit:", self.cuda_found),
            ("Windows SDK:", self.winsdk_found),
            ("MSVC:", self.msvc_found)
        ]
        
        for text, found in items:
            item_widget = QWidget()
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(0, 0, 15, 0)
            
            label = QLabel(text)
            label.setFont(QFont("Segoe UI", 9))
            item_layout.addWidget(label)
            
            status_text = _("Найден", "Found") if found else _("Не найден", "Not Found")
            status_color = "#4CAF50" if found else "#F44336"
            status_label = QLabel(status_text)
            status_label.setFont(QFont("Segoe UI", 9))
            status_label.setStyleSheet(f"color: {status_color};")
            item_layout.addWidget(status_label)
            
            self.status_layout.addWidget(item_widget)
        
        self.status_layout.addStretch()
        
        # Обновляем видимость предупреждения
        if hasattr(self, 'warning_label'):
            self.warning_label.setVisible(not (self.cuda_found and self.winsdk_found and self.msvc_found))

    def _on_refresh_status(self):
        """Обработчик кнопки обновления статуса"""
        logger.info(_("Обновление статуса зависимостей...", "Updating dependency status..."))
        self._check_system_dependencies()
        self._update_status_display()
        logger.info(_("Статус обновлен.", "Status updated."))

    def _uninstall_component(self, component_name: str, main_package_to_remove: str):
        gui_elements = self._create_action_window(
            title=f"Удаление {component_name}", 
            initial_status=f"Удаление {main_package_to_remove}..."
        )
        if not gui_elements: 
            return False
        
        installer = PipInstaller(
            script_path=r"libs\python\python.exe", 
            libs_path="Lib", 
            update_status=gui_elements["update_status"], 
            update_log=gui_elements["update_log"], 
            progress_window=gui_elements["window"]
        )
        
        uninstall_success = installer.uninstall_packages(
            [main_package_to_remove], 
            description=f"Удаление {main_package_to_remove}..."
        )
        
        if uninstall_success:
            cleanup_success = self._cleanup_orphans(installer, gui_elements["update_log"])
            if cleanup_success:
                gui_elements["update_status"]("Удаление завершено.")
            else:
                gui_elements["update_status"]("Ошибка при очистке зависимостей.")
            self._cleanup_after_uninstall(main_package_to_remove)
        else:
            gui_elements["update_status"](f"Ошибка удаления {main_package_to_remove}")

        QTimer.singleShot(3000, gui_elements["window"].close)
        return uninstall_success

    def _cleanup_orphans(self, installer: PipInstaller, update_log_func) -> bool:
        try:
            resolver = DependencyResolver(installer.libs_path_abs, update_log_func)
            all_installed = resolver.get_all_installed_packages()
            known_main = set(canonicalize_name(p) for p in self.known_main_packages)
            protected = canonicalize_name(self.protected_package)

            remaining_main = all_installed & known_main
            required_set = set()
            if protected in all_installed:
                required_set.update(resolver.get_dependency_tree(self.protected_package))
            for pkg in remaining_main:
                required_set.update(resolver.get_dependency_tree(pkg))
            
            orphans = all_installed - required_set
            if orphans:
                orphans_str_list = [str(o) for o in orphans]
                return installer.uninstall_packages(orphans_str_list, "Удаление осиротевших зависимостей...")
            return True
        except Exception as e:
            update_log_func(f"Ошибка во время очистки сирот: {e}")
            return False