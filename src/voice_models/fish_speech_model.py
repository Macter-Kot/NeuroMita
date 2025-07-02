import os
import sys
import importlib
import traceback
import hashlib
from datetime import datetime
import asyncio

from .base_model import IVoiceModel
from typing import Optional, Any
from Logger import logger

from .edge_tts_rvc_model import EdgeTTS_RVC_Model
import importlib.util

import subprocess
from PyQt6.QtCore import QTimer, Qt

from utils.PipInstaller import PipInstaller

from SettingsManager import SettingsManager
def getTranslationVariant(ru_str, en_str=""): return en_str if en_str and SettingsManager.get("LANGUAGE") == "EN" else ru_str
_ = getTranslationVariant

class FishSpeechModel(IVoiceModel):
    def __init__(self, parent: 'LocalVoice', model_id: str, rvc_handler: Optional[IVoiceModel] = None):
        super().__init__(parent, model_id)
        self.fish_speech_module = None
        self.current_fish_speech = None
        self.rvc_handler = rvc_handler

    def _load_module(self):
        try:
            from fish_speech_lib.inference import FishSpeech
            self.fish_speech_module = FishSpeech
        except ImportError as ex:
            self.fish_speech_module = None
            logger.info(ex)


    def get_display_name(self, model_id) -> str:
        mode = self._mode()
        if mode in "medium":
            return "Fish Speech"
        elif mode in "medium+":
            return "Fish Speech+"
        if mode in "medium+low":
            return "Fish Speech+ + RVC"
        return None
    
    def is_installed(self, model_id) -> bool:
        self._load_module()
        mode = model_id

        
        if self.fish_speech_module is None:
            return False
        
        if mode in ("medium+", "medium+low"):
            if not self.parent.is_triton_installed():
                return False
        
        if mode == "medium+low":
            if self.rvc_handler is None or not self.rvc_handler.is_installed("low"):
                return False
        
        return True

    def install(self, model_id) -> bool:
        self._load_module()
        if self.fish_speech_module is None:
            if not self._install_fish_speech():
                return False
        
        mode = model_id
        # Если нужен Triton, ставим его
        if mode in ("medium+", "medium+low"):
            if not self.parent.is_triton_installed():
                logger.info("Компонент Fish Speech установлен, приступаем к установке Triton...")
                if not self._install_triton():
                    return False
        
        # Если нужен RVC, ставим его
        if mode == "medium+low":
            if self.rvc_handler and not self.rvc_handler.is_installed("low"):
                logger.info("Компоненты Fish Speech и Triton установлены, приступаем к установке RVC...")
                return self.rvc_handler.install("low")

        return True

    
    def _install_fish_speech(self):
        gui_elements = None
        try:
            gui_elements = self.parent._create_installation_window(
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

            if self.parent.provider in ["NVIDIA"] and not self.parent.is_cuda_available():
                update_status(_("Установка PyTorch с поддержкой CUDA 12.8...", "Installing PyTorch with CUDA 12.8 support..."))
                update_progress(20)
                success = installer.install_package(
                    ["torch==2.7.1", "torchaudio==2.7.1"],
                    description=_("Установка PyTorch с поддержкой CUDA 12.8...", "Installing PyTorch with CUDA 12.8 support..."),
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu118"],
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
            if self.parent.provider in ["NVIDIA"] or force_install_unsupported:
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
                update_log(_(f"Ошибка: не найдена подходящая видеокарта: {self.parent.provider}", f"Error: suitable graphics card not found: {self.parent.provider}"))
                update_status(_("Требуется NVIDIA GPU", "NVIDIA GPU required"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            update_progress(100)
            update_status(_("Установка успешно завершена!", "Installation successful!"))
            
            self._load_module()
            
            QTimer.singleShot(5000, progress_window.close)
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке Fish Speech: {e}", exc_info=True)
            if gui_elements and gui_elements["window"]:
                gui_elements["window"].close()
            return False

    def _install_triton(self):
        """
        Устанавливает Triton, применяет патчи, проверяет зависимости
        (с возможностью повторной попытки при ошибке DLL) и инициализирует ядро.
        """
        gui_elements = None
        self.parent.triton_module = False 

        try:
            # Определяем режим работы (с внешними колбэками или со своим окном)
            have_external = hasattr(self, "_external_log")
            if have_external:
                progress_window = None
                update_progress = getattr(self, "_external_progress", lambda *_: None)
                update_status = getattr(self, "_external_status", lambda *_: None)
                update_log = getattr(self, "_external_log", lambda *_: None)
            else:
                gui_elements = self.parent._create_installation_window(
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
                "triton-windows<3.4",
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
                self.parent.triton_installed = False
                self.parent.triton_checks_performed = False
                self.parent.cuda_found = False
                self.parent.winsdk_found = False
                self.parent.msvc_found = False

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
                        self.parent._check_system_dependencies()
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
                    
                    user_choice = self.parent._show_vc_redist_warning_dialog()
                    
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
                        progress_window.setWindowModality(Qt.WindowModality.ApplicationModal)

                    if user_choice == "retry" and retries_left > 0:
                        update_log(_("Пользователь выбрал повторить попытку импорта Triton...", "User chose to retry Triton import..."))
                        check_successful = False
                        continue
                    else:
                        if user_choice == "retry":
                            update_log(_("Достигнут лимит попыток для импорта Triton.", "Retry limit reached for Triton import."))
                        else:
                            update_log(_("Пользователь закрыл окно предупреждения VC Redist, не решая проблему.", "User closed the VC Redist warning window without resolving the issue."))
                        check_successful = False
                        break
                else:
                    check_successful = not import_error_occurred and not dependencies_check_error
                    if not check_successful:
                        if import_error_occurred:
                            update_log(_("Проверка зависимостей не удалась из-за ошибки импорта (не DLL).", "Dependency check failed due to import error (not DLL)."))
                        elif dependencies_check_error:
                            update_log(_("Проверка зависимостей не удалась из-за ошибки внутри _check_system_dependencies.", "Dependency check failed due to an error within _check_system_dependencies."))
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
                self.parent.triton_module = False
            elif self.parent.triton_installed and self.parent.triton_checks_performed:
                self.parent.triton_module = True
                if not (self.parent.cuda_found and self.parent.winsdk_found and self.parent.msvc_found):
                    update_log(_("Обнаружено отсутствие зависимостей (CUDA/WinSDK/MSVC).", "Missing dependencies detected (CUDA/WinSDK/MSVC)."))
                    update_status(_("Требуется внимание: зависимости Triton", "Attention required: Triton dependencies"))
                    
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setWindowModality(Qt.WindowModality.NonModal)
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, False)
                    
                    user_action_deps = self.parent._show_triton_init_warning_dialog()
                    
                    if progress_window and hasattr(progress_window, 'isVisible') and progress_window.isVisible():
                        progress_window.setAttribute(Qt.WidgetAttribute.WA_AlwaysStackOnTop, True)
                        progress_window.setWindowModality(Qt.WindowModality.ApplicationModal)
                else:
                    update_log(_("Все зависимости Triton (CUDA, WinSDK, MSVC) найдены.", "All Triton dependencies (CUDA, WinSDK, MSVC) found."))
                    skip_init = False
            else:
                update_log(_("Неожиданное состояние после проверки зависимостей (check_successful=True, но флаги не установлены). Пропуск инициализации ядра.", "Unexpected state after dependency check (check_successful=True, but flags not set). Skipping kernel initialization."))
                skip_init = True
                self.parent.triton_module = False

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

            if check_successful and not skip_init and not (self.parent.cuda_found and self.parent.winsdk_found and self.parent.msvc_found):
                missing_deps = [dep for dep, found in [("CUDA", self.parent.cuda_found), ("WinSDK", self.parent.winsdk_found), ("MSVC", self.parent.msvc_found)] if not found]
                final_message += _(f" Внимание: не найдены зависимости ({', '.join(missing_deps)})!", f" Warning: missing dependencies ({', '.join(missing_deps)})!")

            update_status(final_message)
            update_log(final_message)

            # Добавляем финальный совет
            if not check_successful:
                update_log(_("Если модель medium+ не заработает, проверьте лог, зависимости (особенно VC Redist) и документацию.", "If the medium+ model doesn't work, check the log, dependencies (especially VC Redist), and documentation."))
            elif skip_init:
                update_log(_("Если модель medium+ не заработает, возможно, потребуется запустить init_triton.bat вручную.", "If the medium+ model doesn't work, you might need to run init_triton.bat manually."))
            elif not (self.parent.cuda_found and self.parent.winsdk_found and self.parent.msvc_found):
                update_log(_("Если модель medium+ не заработает, проверьте установку недостающих зависимостей (CUDA/WinSDK/MSVC).", "If the medium+ model doesn't work, check the installation of missing dependencies (CUDA/WinSDK/MSVC)."))

            self.parent.triton_installed = True
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
            self.parent.triton_module = False
            return False

    def uninstall(self, model_id) -> bool:
        
        mode = model_id
        if mode == "medium":
            return self.parent._uninstall_component("Fish Speech", "fish-speech-lib")
        elif mode in ("medium+", "medium+low"):
            return self.parent._uninstall_component("Triton", "triton-windows")
        else: 
            logger.error(_('Неизвестная модель для удаления.', 'Unknown model for uninstall'))
            return False

    def cleanup_state(self):
        super().cleanup_state()
        self.current_fish_speech = None
        self.fish_speech_module = None
        if self.parent.first_compiled is not None:
            logger.info("Сброс состояния компиляции Fish Speech из-за удаления.")
            self.parent.first_compiled = None

        if self.rvc_handler and self.rvc_handler.initialized:
            self.rvc_handler.cleanup_state()

        logger.info(f"Состояние для модели {self.model_id} сброшено.")

    def initialize(self, init: bool = False) -> bool:
        if self.initialized:
            return True

        self._load_module()
        if self.fish_speech_module is None:
            logger.error("fish_speech_lib не установлен")
            return False

        mode = self._mode()
        compile_model = mode in ("medium+", "medium+low")

        if (self.parent.first_compiled is not None 
                and self.parent.first_compiled != compile_model):
            logger.error(
                "КОНФЛИКТ: нельзя переключиться между compile=True/False без перезапуска")
            return False

        if self.current_fish_speech is None:
            settings = self.parent.load_model_settings(mode)
            device = settings.get(
                "fsprvc_fsp_device" if mode == "medium+low" else "device",
                "cuda")
            half = settings.get(
                "fsprvc_fsp_half"  if mode == "medium+low" else "half",
                "True" if compile_model else "False").lower() == "true"

            self.current_fish_speech = self.fish_speech_module(
                device=device, half=half, compile_model=compile_model)

            self.parent.first_compiled = compile_model
            logger.info(f"FishSpeech инициализирован (compile={compile_model})")

        if mode == "medium+low":
            if self.rvc_handler and not self.rvc_handler.initialized:
                logger.info("Инициализация RVC компонента для 'medium+low'...")
                rvc_success = self.rvc_handler.initialize(init=False)
                if not rvc_success:
                    logger.error("Не удалось инициализировать RVC компонент для 'medium+low'.")
                    return False

        self.initialized = True

        if init:
            init_text = f"Инициализация модели {self.model_id}" if self.parent.voice_language == "ru" else f"{self.model_id} Model Initialization"
            logger.info(f"Выполнение тестового прогона для {self.model_id}...")
            try:
                main_loop = self.parent.parent.loop
                if not main_loop or not main_loop.is_running():
                    raise RuntimeError("Главный цикл событий asyncio недоступен.")
                
                future = asyncio.run_coroutine_threadsafe(self.voiceover(init_text), main_loop)
                result = future.result(timeout=3600)
                
                logger.info(f"Тестовый прогон для {self.model_id} успешно завершен.")
            except Exception as e:
                logger.error(f"Ошибка во время тестового прогона модели {self.model_id}: {e}", exc_info=True)
                self.initialized = False
                return False

        return True

    async def voiceover(self, text: str, character: Optional[Any] = None, **kwargs) -> Optional[str]:
        if not self.initialized:
            raise Exception(f"Модель {self.model_id} не инициализирована.")
            
        if self.fish_speech_module is None:
            raise ImportError("Модуль fish_speech_lib не установлен.")

        try:
            mode = self._mode()
            settings = self.parent.load_model_settings(mode)
            is_combined_model = mode == "medium+low"
            
            temp_key = "fsprvc_fsp_temperature" if is_combined_model else "temperature"
            top_p_key = "fsprvc_fsp_top_p" if is_combined_model else "top_p"
            rep_penalty_key = "fsprvc_fsp_repetition_penalty" if is_combined_model else "repetition_penalty"
            chunk_len_key = "fsprvc_fsp_chunk_length" if is_combined_model else "chunk_length"
            max_tokens_key = "fsprvc_fsp_max_tokens" if is_combined_model else "max_new_tokens"
            seed_key = "fsprvc_fsp_seed" if is_combined_model else "seed"

            reference_audio_path = self.parent.clone_voice_filename if self.parent.clone_voice_filename and os.path.exists(self.parent.clone_voice_filename) else None
            reference_text = ""
            if reference_audio_path and self.parent.clone_voice_text and os.path.exists(self.parent.clone_voice_text):
                with open(self.parent.clone_voice_text, "r", encoding="utf-8") as file:
                    reference_text = file.read().strip()

            seed_processed = int(settings.get(seed_key, 0))
            if seed_processed <= 0 or seed_processed > 2**31 - 1: seed_processed = 42

            sample_rate, audio_data = self.current_fish_speech(
                text=text,
                reference_audio=reference_audio_path,
                reference_audio_text=reference_text,
                top_p=float(settings.get(top_p_key, 0.7)),
                temperature=float(settings.get(temp_key, 0.7)),
                repetition_penalty=float(settings.get(rep_penalty_key, 1.2)),
                max_new_tokens=int(settings.get(max_tokens_key, 1024)),
                chunk_length=int(settings.get(chunk_len_key, 200)),
                seed=seed_processed,
                use_memory_cache=True,
            )

            hash_object = hashlib.sha1(f"{text[:20]}_{datetime.now().timestamp()}".encode())
            raw_output_filename = f"fish_raw_{hash_object.hexdigest()[:10]}.wav"
            raw_output_path = os.path.abspath(os.path.join("temp", raw_output_filename))
            os.makedirs("temp", exist_ok=True)
            
            import soundfile as sf
            sf.write(raw_output_path, audio_data, sample_rate)

            if not os.path.exists(raw_output_path) or os.path.getsize(raw_output_path) == 0:
                return None

            stereo_output_path = raw_output_path.replace("_raw", "_stereo")
            converted_file = self.parent.convert_wav_to_stereo(raw_output_path, stereo_output_path, volume="1.5")
            
            processed_output_path = stereo_output_path if converted_file and os.path.exists(converted_file) else raw_output_path
            if processed_output_path == stereo_output_path:
                try: os.remove(raw_output_path)
                except OSError: pass
            
            final_output_path = processed_output_path

            if mode == "medium+low":
                if self.rvc_handler:
                    logger.info(f"Применяем RVC с параметрами FSP+RVC к файлу: {final_output_path}")
                    
                    # Получаем fsp_rvc параметры из настроек
                    rvc_output_path = await self.rvc_handler.apply_rvc_to_file(
                        filepath=final_output_path,
                        pitch=float(settings.get("fsprvc_rvc_pitch", 0)),
                        index_rate=float(settings.get("fsprvc_index_rate", 0.75)),
                        protect=float(settings.get("fsprvc_protect", 0.33)),
                        filter_radius=int(settings.get("fsprvc_filter_radius", 3)),
                        rms_mix_rate=float(settings.get("fsprvc_rvc_rms_mix_rate", 0.5)),
                        is_half=settings.get("fsprvc_is_half", "True").lower() == "true",
                        f0method=settings.get("fsprvc_f0method", None),
                        use_index_file=settings.get("fsprvc_use_index_file", True)
                    )
                    
                    if rvc_output_path and os.path.exists(rvc_output_path):
                        if final_output_path != rvc_output_path:
                            try: os.remove(final_output_path)
                            except OSError: pass
                        final_output_path = rvc_output_path
                    else:
                        logger.warning("Ошибка во время обработки RVC. Возвращается результат до RVC.")
                else:
                    logger.warning("Модель 'medium+low' требует RVC, но обработчик не был предоставлен.")

            if self.parent.parent and hasattr(self.parent.parent, 'patch_to_sound_file'):
                self.parent.parent.patch_to_sound_file = final_output_path
            
            return final_output_path
        except Exception as error:
            traceback.print_exc()
            logger.info(f"Ошибка при создании озвучки с Fish Speech ({self.model_id}): {error}")
            return None
        
    def _mode(self) -> str:
        """
        Возвращает текущий «режим» (medium / medium+ / medium+low),
        выбранный в LocalVoice.initialize_model().
        Если по какой-то причине ещё не выбран – по умолчанию medium.
        """
        return (self.parent.current_model_id or "medium")