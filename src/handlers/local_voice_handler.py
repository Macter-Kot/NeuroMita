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
from utils.gpu_utils import check_gpu_provider

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
from utils.pip_installer import PipInstaller, DependencyResolver
from managers.settings_manager import SettingsManager

# --- Новые импорты для модульной структуры ---
from handlers.voice_models.base_model import IVoiceModel
from handlers.voice_models.edge_tts_rvc_model import EdgeTTS_RVC_Model
from handlers.voice_models.fish_speech_model import FishSpeechModel
from handlers.voice_models.f5_tts_model import F5TTSModel

from docs import DocsManager
from main_logger import logger

from utils import getTranslationVariant as _


# ──────────────────────────────────────────────────────────────
#  ДОБАВИТЬ в начало файла (после других импортов Qt)
from PyQt6.QtCore import QMetaObject, QThread, Qt, QObject
# ──────────────────────────────────────────────────────────────

# ===== 1.  Утилита для «безопасного» вызова GUI из воркера =====
def _call_in_main_thread(fn, *args, **kwargs):
    """
    Гарантирует выполнение fn в GUI-потоке и возвращает его результат.
    Используется для показа диалоговых окон из фоновых потоков.
    """
    app = QApplication.instance()
    if QThread.currentThread() == app.thread():
        return fn(*args, **kwargs)

    ret_holder = {}

    def _wrapper():
        ret_holder["result"] = fn(*args, **kwargs)

    QMetaObject.invokeMethod(
        app,
        _wrapper,         
        Qt.ConnectionType.BlockingQueuedConnection
    )
    return ret_holder.get("result")

class LocalVoice:
    def __init__(self, parent=None):
        self.parent = parent
        self.settings = parent.settings if parent else SettingsManager()
        
        self.first_compiled: Optional[bool] = None

        self.current_model_id: Optional[str] = None
        self.active_model_instance: Optional[IVoiceModel] = None
        
        # Создаем один экземпляр для всех RVC-моделей
        edge_rvc_handler = EdgeTTS_RVC_Model(self, "edge_rvc_handler")
        fish_handler = FishSpeechModel(self, "fish_handler", rvc_handler=edge_rvc_handler)
        f5_handler = F5TTSModel(self, "f5_handler", rvc_handler=edge_rvc_handler)

        self.models: Dict[str, IVoiceModel] = {
            "low": edge_rvc_handler,
            "low+": edge_rvc_handler,
            "medium":        fish_handler,
            "medium+":       fish_handler,
            "medium+low":    fish_handler,
            "high": f5_handler,
            "high+low": f5_handler,
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
        self.protected_packages = ["g4f", "gigaam", "pillow", "silero-vad"]
        
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
            ok = model.install(model_id)
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
        
        if not model_to_init.is_installed(model_id):
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
            return model.is_installed(model_id)
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
        return self.models["low"].uninstall("low")

    def uninstall_fish_speech(self):
        return self.models["medium"].uninstall("medium")

    def uninstall_f5_tts(self):
        return self.models["high"].uninstall("high")

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
            model_to_reset_ids = ["high", "high+low"]
            
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


    def select_model(self, model_id: str) -> None:
        """
        Делает указанную ИНИЦИАЛИЗИРОВАННУЮ модель активной.
        Исключений не бросает – вызывающий уже проверил is_model_initialized().
        """
        model = self.models.get(model_id)
        if not model or not model.initialized:
            raise RuntimeError(f"Model '{model_id}' is not initialised")
        self.current_model_id      = model_id
        self.active_model_instance = model
        logger.info(f"Active local voice model set to '{model_id}'")

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

    def convert_wav_to_stereo(
        self,
        input_path      : str,
        output_path     : str,
        *,
        atempo : float  = 1.0,
        volume : str    = "1.0",
        pitch  : float  = 0.0,
        show_call_stack: bool = False,
        save_err_to    : str | None = None   # путь для сохранения stderr
    ) -> str | None:
        """
        Конвертирует WAV → стерео WAV.
        При ошибке:
        •  логирует полный traceback,
        •  выводит stderr FFmpeg,
        •  (опция) записывает stderr в файл.
        """

        if show_call_stack:
            logger.debug(
                "[convert_wav_to_stereo] call-stack:\n" +
                "".join(traceback.format_stack(limit=15))
            )

        if not os.path.exists(input_path):
            err = f"Файл не найден: {input_path}"
            logger.error(err)
            raise FileNotFoundError(err)

        try:
            pitch_ratio = 2 ** (pitch / 12.0)
            # ───────── запуск FFmpeg ─────────
            out, err = (
                ffmpeg
                .input(input_path)
                .filter("rubberband", pitch=pitch_ratio, pitchq="quality")
                .filter("atempo", atempo)
                .filter("volume", volume=volume)
                .output(
                    output_path,
                    format="wav",
                    acodec="pcm_s16le",
                    ar="44100",
                    ac=2
                )
                .run(
                    cmd=["ffmpeg", "-nostdin"],
                    capture_stdout=True,
                    capture_stderr=True,
                    overwrite_output=True
                )
            )
            # Можно залогировать вывод, если нужен
            logger.debug(f"FFmpeg stdout:\n{out.decode(errors='ignore')}")
            return output_path

        except ffmpeg.Error as fe:
            # Здесь уже полноценный трейс + stderr FFmpeg
            tb = traceback.format_exc()
            ff_err = fe.stderr.decode(errors="ignore") if fe.stderr else "«stderr пуст»"

            logger.error(
                "[convert_wav_to_stereo] FFmpeg ERROR\n" +
                "-"*60 + "\n" +
                ff_err + "\n" +
                "-"*60 + "\n" +
                tb
            )

            # Сохраняем stderr на диск (по желанию)
            if save_err_to:
                try:
                    with open(save_err_to, "w", encoding="utf-8", errors="ignore") as f:
                        f.write(ff_err)
                    logger.info(f"stderr FFmpeg сохранён в {save_err_to}")
                except Exception as save_e:
                    logger.warning(f"Не удалось сохранить stderr: {save_e}")

            raise   # пробрасываем наружу – пусть вызывающий решает, что делать

        except Exception:
            # Любая другая ошибка
            logger.error("[convert_wav_to_stereo] Unexpected error:\n" + traceback.format_exc())
            raise

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
            dialog.setWindowFlags(dialog.windowFlags())
            
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
        if QThread.currentThread() != QApplication.instance().thread():
            return _call_in_main_thread(self._show_vc_redist_warning_dialog)
        
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
        if QThread.currentThread() != QApplication.instance().thread():
            return _call_in_main_thread(self._show_triton_init_warning_dialog)
        
        dialog = QDialog(self.parent if self.parent and hasattr(self.parent, 'isVisible') else None)
        dialog.setWindowTitle(_("⚠️ Зависимости Triton", "⚠️ Triton Dependencies"))
        dialog.setModal(True)
        dialog.setFixedSize(700, 350)
        
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

    def _uninstall_component(self, component_name: str, main_package_to_remove: str) -> bool:
        gui_elements = self._create_action_window(
            title=_(f"Удаление {component_name}", f"Uninstalling {component_name}"),
            initial_status=_(f"Удаление {main_package_to_remove}...", f"Uninstalling {main_package_to_remove}...")
        )
        if not gui_elements:
            return False

        try:
            update_status = gui_elements["update_status"]
            update_log = gui_elements["update_log"]

            installer = PipInstaller(
                script_path=r"libs\python\python.exe", libs_path="Lib",
                update_status=update_status, update_log=update_log,
                progress_window=gui_elements["window"]
            )

            # Этап 1: Удаление основного пакета
            update_log(_(f"Удаление '{main_package_to_remove}'...", f"Uninstalling '{main_package_to_remove}'..."))
            uninstall_success = installer.uninstall_packages(
                [main_package_to_remove],  # Позиционный аргумент: список пакетов
                _(f"Удаление {main_package_to_remove}...", f"Uninstalling {main_package_to_remove}...")
            )

            if not uninstall_success:
                update_log(_(f"Не удалось удалить '{main_package_to_remove}'.", f"Failed to uninstall '{main_package_to_remove}'."))
                update_status(_(f"Ошибка удаления {main_package_to_remove}", f"Error uninstalling {main_package_to_remove}"))
                return False

            # Этап 2: Очистка orphans
            update_status(_("Очистка зависимостей...", "Cleaning up dependencies..."))
            update_log(_("Поиск 'осиротевших' зависимостей...", "Finding 'orphaned' dependencies..."))
            cleanup_success = self._cleanup_orphans(installer, update_log)

            # Финал
            if cleanup_success:
                update_status(_("Удаление завершено.", "Uninstallation complete."))
                update_log(_("Очистка завершена.", "Cleanup complete."))
            else:
                update_status(_("Ошибка очистки.", "Cleanup error."))
                update_log(_("Не удалось удалить некоторые зависимости.", "Failed to remove some dependencies."))

            self._cleanup_after_uninstall(main_package_to_remove)
            if cleanup_success:
                QTimer.singleShot(3000, gui_elements["window"].close)
            return uninstall_success and cleanup_success

        except Exception as e:
            logger.error(f"Ошибка при удалении {component_name}: {e}")
            traceback.print_exc()
            if gui_elements and gui_elements["window"].isVisible():
                gui_elements["update_log"](f"{_('Ошибка:', 'Error:')} {e}\n{traceback.format_exc()}")
                gui_elements["update_status"](_("Критическая ошибка!", "Critical error!"))
                QTimer.singleShot(5000, gui_elements["window"].close)
            return False

    def _cleanup_orphans(self, installer: PipInstaller, update_log_func) -> bool:
        try:
            resolver = DependencyResolver(installer.libs_path_abs, update_log_func)
            all_installed_canon = resolver.get_all_installed_packages()  # set[NormalizedName]
            known_main_canon = set(canonicalize_name(p) for p in self.known_main_packages)
            remaining_main_canon = all_installed_canon & known_main_canon

            # Защищённые пакеты и их deps (универсально для списка)
            protected_deps_canon = set()
            for prot_pkg in self.protected_packages:
                prot_canon = canonicalize_name(prot_pkg)
                if prot_canon in all_installed_canon:
                    deps = resolver.get_dependency_tree(prot_pkg) or {prot_canon}  # Включаем себя, если deps пустые
                    protected_deps_canon.update(deps)
                    update_log_func(_(f"Зависимости {prot_pkg}: {deps or 'Нет'}", f"Dependencies of {prot_pkg}: {deps or 'None'}"))

            # Deps оставшихся main пакетов
            other_required_deps_canon = set()
            for pkg_canon in remaining_main_canon:
                deps = resolver.get_dependency_tree(str(pkg_canon)) or {pkg_canon}  # str на случай, если нужно original
                other_required_deps_canon.update(deps)

            required_set_canon = protected_deps_canon | other_required_deps_canon
            orphans_canon = all_installed_canon - required_set_canon

            if not orphans_canon:
                update_log_func(_("Осиротевшие не найдены.", "No orphans found."))
                return True

            # Получаем original names из dist-info
            installed_packages_map = {}
            if os.path.exists(installer.libs_path_abs):
                for item in os.listdir(installer.libs_path_abs):
                    if item.endswith(".dist-info"):
                        try:
                            dist_name = item.split('-')[0]
                            installed_packages_map[canonicalize_name(dist_name)] = dist_name
                        except Exception:
                            pass

            orphans_original_names = [installed_packages_map.get(o, str(o)) for o in orphans_canon]
            update_log_func(_(f"Удаление сирот: {orphans_original_names}", f"Uninstalling orphans: {orphans_original_names}"))

            return installer.uninstall_packages(
                orphans_original_names,  # Позиционный аргумент: список пакетов
                _("Удаление осиротевших...", "Uninstalling orphaned...")
            )

        except Exception as e:
            update_log_func(_(f"Ошибка очистки: {e}", f"Cleanup error: {e}"))
            update_log_func(traceback.format_exc())
            return False