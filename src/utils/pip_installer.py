"""
PipInstaller 3.0
"""

from __future__ import annotations
import subprocess, sys, os, queue, threading, time, json, shutil, gc, importlib.util
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, NormalizedName
from packaging.version import parse as parse_version
from main_logger import logger
from PyQt6.QtWidgets import QApplication
from typing import Set, List, Tuple, Optional
from PyQt6.QtCore import QThread, QCoreApplication

class DependencyResolver:
    def __init__(self, libs_path_abs, update_log_func):
        self.libs_path = libs_path_abs
        self.update_log = update_log_func
        self.cache_file_path = os.path.join(self.libs_path, "dependency_cache.json")
        self._dist_info_cache: dict[NormalizedName, str | None] = {}
        self._dep_cache: dict[NormalizedName, set[NormalizedName]] = {}
        self._tree_cache = self._load_tree_cache()

    def _load_tree_cache(self):
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as ex:
                logger.error("Ошибка при _load_tree_cache: " + str(ex))
        return {}

    def _save_tree_cache(self):
        try:
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                json.dump(self._tree_cache, f, indent=4)
        except Exception as ex:
            logger.error("Ошибка при _save_tree_cache: " + str(ex))

    def _find_dist_info_path(self, package_name_canon: NormalizedName):
        cached = self._dist_info_cache.get(package_name_canon)
        if cached is not None:
            return cached
        if not os.path.exists(self.libs_path):
            logger.warning(f"Директория {self.libs_path} не существует для поиска dist-info.")
            self._dist_info_cache[package_name_canon] = None
            return None
        logger.debug(f"Сканирование {self.libs_path} для {package_name_canon}")
        for item in os.listdir(self.libs_path):
            if item.endswith(".dist-info"):
                try:
                    dist_name = item.split("-")[0]
                    if canonicalize_name(dist_name) == package_name_canon:
                        p = os.path.join(self.libs_path, item)
                        self._dist_info_cache[package_name_canon] = p
                        logger.debug(f"Найден dist-info для {package_name_canon}: {p}")
                        return p
                except Exception as ex:
                    logger.debug(f"Пропуск повреждённого dist-info {item}: {ex}")
                    continue
        self._dist_info_cache[package_name_canon] = None
        return None

    def _get_package_version(self, package_name_canon: NormalizedName):
        dist_path = self._find_dist_info_path(package_name_canon)
        if not dist_path:
            return None
        try:
            parts = os.path.basename(dist_path).split("-")
            if len(parts) >= 2 and parts[-1] == "dist-info":
                v = parts[-2]
                if v and v[0].isdigit():
                    return str(parse_version(v))
        except Exception as ex:
            logger.error("Ошибка при _get_package_version: " + str(ex))
        meta = os.path.join(dist_path, "METADATA")
        if os.path.exists(meta):
            try:
                with open(meta, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.lower().startswith("version:"):
                            return line.split(":", 1)[1].strip()
            except Exception as ex:
                logger.error("Ошибка при _get_package_version (METADATA): " + str(ex))
        return None

    def _get_direct_dependencies(self, package_name_canon: NormalizedName):
        cached = self._dep_cache.get(package_name_canon)
        if cached is not None:
            return cached
        deps: set[NormalizedName] = set()
        dist_path = self._find_dist_info_path(package_name_canon)
        if dist_path:
            meta = os.path.join(dist_path, "METADATA")
            if os.path.exists(meta):
                try:
                    with open(meta, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.lower().startswith("requires-dist:"):
                                req_str = line.split(":", 1)[1].strip()
                                try:
                                    req_part = req_str.split(";")[0].strip()
                                    if req_part:
                                        deps.add(canonicalize_name(Requirement(req_part).name))
                                except Exception as ex:
                                    logger.error("Ошибка парсинга requires-dist: " + str(ex))
                except Exception as ex:
                    logger.error("Ошибка чтения METADATA: " + str(ex))
        self._dep_cache[package_name_canon] = deps
        logger.debug(f"Direct deps for {package_name_canon}: {deps}")
        return deps

    def get_dependency_tree(self, root_package_name: str):
        root_canon = canonicalize_name(root_package_name)
        ver = self._get_package_version(root_canon)
        if not ver:
            if root_canon in self._tree_cache:
                del self._tree_cache[root_canon]
                self._save_tree_cache()
            return set()
        cached = self._tree_cache.get(root_canon)
        if cached and cached.get("version") == ver:
            return set(cached.get("dependencies", []))
        required: set[NormalizedName] = {root_canon}
        q: list[NormalizedName] = [root_canon]
        processed: set[NormalizedName] = set()
        self._dist_info_cache.clear()
        self._dep_cache.clear()
        while q:
            cur = q.pop(0)
            if cur in processed:
                continue
            processed.add(cur)
            for dep in self._get_direct_dependencies(cur):
                if dep not in required:
                    required.add(dep)
                    if dep not in processed:
                        q.append(dep)
        self._tree_cache[root_canon] = {"version": ver, "dependencies": sorted(required)}
        self._save_tree_cache()
        logger.debug(f"Dependency tree for {root_package_name}: {required}")
        return required

    def get_all_installed_packages(self):
        pkgs = set()
        if os.path.exists(self.libs_path):
            logger.debug(f"Сканирование всех пакетов в {self.libs_path}")
            for item in os.listdir(self.libs_path):
                if item.endswith(".dist-info"):
                    try:
                        pkg_name = canonicalize_name(item.split("-")[0])
                        pkgs.add(pkg_name)
                        logger.debug(f"Найден пакет: {pkg_name}")
                    except Exception as ex:
                        logger.error("Ошибка при get_all_installed_packages: " + str(ex))
        else:
            logger.warning(f"Директория {self.libs_path} не существует для get_all_installed_packages.")
        logger.debug(f"Все установленные пакеты: {pkgs}")
        return pkgs


class PipInstaller:
    def __init__(
        self,
        script_path: str,
        libs_path: str = "Lib",
        update_status=None,
        update_log=None,
        progress_window=None,
        update_progress=None,
        protected_packages: Optional[List[str]] = None
    ):
        self.script_path = script_path
        self.libs_path = libs_path
        self.python_root = Path(script_path).resolve().parent
        self.libs_path_abs = os.path.abspath(self.libs_path)
        self.update_status = update_status or (lambda m: logger.info(f"STATUS: {m}"))
        self.update_log = update_log or (lambda m: logger.info(f"LOG: {m}"))
        self.update_progress = update_progress or (lambda *_: None)
        self.progress_window = progress_window
        # Защищенные пакеты по умолчанию
        self.protected_packages = protected_packages or ["g4f", "gigaam", "pillow", "silero-vad"]
        self._ensure_libs_path()

    def install_package(self, package_spec, description="Установка пакета...", extra_args=None) -> bool:
        cmd = [
            self.script_path, "-m", "uv", "pip", "install",
            "--target", str(self.libs_path_abs),
            "--no-cache-dir"
        ]
        if extra_args:
            cmd.extend(extra_args)
        if isinstance(package_spec, list):
            cmd.extend(package_spec)
        else:
            cmd.append(package_spec)
        return self._run_pip_process(cmd, description)

    def _unload_module_from_sys(self, module_name: str):
        """Выгружает модуль и все его подмодули из sys.modules"""
        to_remove = []
        
        # Ищем все модули, которые начинаются с module_name
        for loaded_name in list(sys.modules.keys()):
            if loaded_name == module_name or loaded_name.startswith(module_name + "."):
                to_remove.append(loaded_name)
        
        # Также проверяем вариант с заменой - на _
        alt_name = module_name.replace("-", "_") if "-" in module_name else module_name.replace("_", "-")
        if alt_name != module_name:
            for loaded_name in list(sys.modules.keys()):
                if loaded_name == alt_name or loaded_name.startswith(alt_name + "."):
                    to_remove.append(loaded_name)
        
        # Удаляем найденные модули
        for mod_name in to_remove:
            try:
                if mod_name in sys.modules:
                    self.update_log(f"Выгружаем модуль из памяти: {mod_name}")
                    del sys.modules[mod_name]
            except Exception as e:
                logger.warning(f"Не удалось выгрузить модуль {mod_name}: {e}")
        
        # Принудительная сборка мусора
        gc.collect()

    def _is_protected_dependency(self, package_canon: NormalizedName, protected_deps: Set[NormalizedName]) -> bool:
        """Проверяет, является ли пакет защищенной зависимостью"""
        return package_canon in protected_deps

    def uninstall_packages(self, packages: List[str], description="Удаление пакетов...") -> bool:
        if not packages:
            self.update_log("Список пакетов для удаления пуст.")
            return True

        resolver = DependencyResolver(self.libs_path_abs, self.update_log)
        requested: Set[NormalizedName] = {canonicalize_name(p) for p in packages}
        
        # Основные пакеты для удаления
        main_packages_to_remove = packages.copy()
        self.update_log(f"Запрошено удаление пакетов: {main_packages_to_remove}")

        # Собираем защищенные пакеты и их зависимости
        protected_canon = {canonicalize_name(p) for p in self.protected_packages}
        protected_deps: Set[NormalizedName] = set()
        
        all_installed = resolver.get_all_installed_packages()
        
        for prot_pkg in self.protected_packages:
            prot_canon = canonicalize_name(prot_pkg)
            if prot_canon in all_installed:
                deps = resolver.get_dependency_tree(prot_pkg) or {prot_canon}
                protected_deps.update(deps)
                self.update_log(f"Защищенный пакет {prot_pkg} и его зависимости: {deps}")

        # Собираем все зависимости удаляемых пакетов
        candidates: Set[NormalizedName] = set()
        for pkg in requested:
            candidates.update(resolver.get_dependency_tree(str(pkg)))
        candidates.update(requested)
        
        # Исключаем защищенные пакеты из кандидатов на удаление
        final_remove = sorted(candidates - protected_deps)
        
        self.update_log(f"Кандидаты на удаление (исключая защищенные): {final_remove}")

        if not final_remove:
            self.update_log("Нечего удалять: все пакеты либо защищены, либо не найдены.")
            return True

        # Переменные для отслеживания успеха
        main_packages_removed = []
        dependencies_failed = []
        
        # Сначала выгружаем все модули из памяти (кроме защищенных)
        self.update_log("Выгружаем модули из памяти...")
        for pkg in final_remove:
            if not self._is_protected_dependency(canonicalize_name(pkg), protected_deps):
                self._unload_module_from_sys(str(pkg))

        # Удаляем пакеты
        for pkg in final_remove:
            canon = canonicalize_name(pkg)
            is_main_package = str(pkg) in main_packages_to_remove or canon in requested
            
            dist_path = self._find_dist_info_path(canon)
            
            if dist_path:
                # Пробуем удалить через uv
                cmd = [
                    self.script_path, "-m", "uv", "pip", "uninstall",
                    "--target", str(self.libs_path_abs), str(pkg)
                ]
                success = self._run_pip_process(cmd, f"Удаление {pkg}")
                
                if not success:
                    # Если не удалось через uv, пробуем ручное удаление
                    self.update_log(f"uv pip не смог удалить {pkg}, пробуем ручное удаление...")
                    success = self._manual_remove(dist_path, str(pkg))
                
                if success and is_main_package:
                    main_packages_removed.append(str(pkg))
                elif not success and not is_main_package:
                    dependencies_failed.append(str(pkg))
                elif not success and is_main_package:
                    # Основной пакет не удалился - это ошибка
                    self.update_log(f"ОШИБКА: Не удалось удалить основной пакет {pkg}")
                    return False
            else:
                self.update_log(f"{pkg}: dist-info не найден, считаем удалённым.")
                if is_main_package:
                    main_packages_removed.append(str(pkg))

        # Проверяем результат
        if main_packages_removed:
            self.update_log(f"Успешно удалены основные пакеты: {main_packages_removed}")
            if dependencies_failed:
                self.update_log(f"Некоторые зависимости не удалились (это нормально): {dependencies_failed}")
            self.update_log("Удаление завершено успешно.")
            return True
        else:
            self.update_log("ОШИБКА: Не удалось удалить ни одного основного пакета.")
            return False

    def _manual_remove(self, path: str, pkg_name: str) -> bool:
        if not os.path.exists(path):
            return True

        retries = 5
        wait = [0.5, 1, 2, 3, 5]
        
        # Попытки удаления с задержками
        for attempt in range(retries):
            try:
                # Сначала пробуем обычное удаление
                shutil.rmtree(path, ignore_errors=False)
                if not os.path.exists(path):
                    logger.info(f"{pkg_name}: каталог {path} удалён.")
                    return True
            except Exception as ex:
                logger.warning(
                    f"{pkg_name}: не удалось удалить (попытка {attempt+1}/{retries}): {ex}"
                )
                
                # Дополнительная очистка перед следующей попыткой
                self._unload_module_from_sys(pkg_name)
                gc.collect()
                time.sleep(wait[attempt])

        # Последняя попытка с игнорированием ошибок
        try:
            shutil.rmtree(path, ignore_errors=True)
        except Exception:
            pass

        # Финальная проверка
        if os.path.exists(path):
            logger.error(f"{pkg_name}: не удалось удалить каталог {path} после всех попыток.")
            return False
        
        logger.info(f"{pkg_name}: каталог {path} удалён после нескольких попыток.")
        return True

    def _find_dist_info_path(self, package_name_canon: NormalizedName) -> str | None:
        if not os.path.exists(self.libs_path_abs):
            return None
        for item in os.listdir(self.libs_path_abs):
            if item.endswith(".dist-info"):
                try:
                    dist_name = item.split("-")[0]
                    if canonicalize_name(dist_name) == package_name_canon:
                        return os.path.join(self.libs_path_abs, item)
                except Exception:
                    continue
        return None

    def _ensure_libs_path(self):
        os.makedirs(self.libs_path_abs, exist_ok=True)
        if self.libs_path_abs not in sys.path:
            sys.path.insert(0, self.libs_path_abs)

    def _run_pip_process(self, cmd: list[str], description: str) -> bool:
        is_qt_window = hasattr(self.progress_window, "isVisible") and callable(self.progress_window.isVisible)
        self.update_status(description)
        self.update_log("Выполняем: " + " ".join(cmd))
        env = os.environ.copy()
        
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env=env
            )
        except FileNotFoundError:
            self.update_log("ОШИБКА: не найден интерпретатор Python.")
            return False
        except Exception as e:
            self.update_log(f"ОШИБКА запуска subprocess: {e}")
            return False
            
        q_out, q_err = queue.Queue(), queue.Queue()

        def _reader(pipe, q):
            try:
                for line in iter(pipe.readline, ""):
                    q.put(line.rstrip())
            finally:
                pipe.close()

        threading.Thread(target=_reader, args=(proc.stdout, q_out), daemon=True).start()
        threading.Thread(target=_reader, args=(proc.stderr, q_err), daemon=True).start()
        
        start = time.time()
        last_activity = start
        TIMEOUT_SEC = 7200000
        NO_ACTIVITY_SEC = 3600000
        progress_sofar = 0
        
        while proc.poll() is None:
            if is_qt_window and not self.progress_window.isVisible():
                self.update_log("Окно закрыто, прерываем процесс.")
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
                return False
                
            msgs = 0
            while not q_out.empty():
                self.update_log(q_out.get_nowait())
                msgs += 0.4
            while not q_err.empty():
                msg = q_err.get_nowait()
                self.update_log(msg)
                if "not installed" in msg.lower() or "no such" in msg.lower():
                    logger.debug(f"UV сообщает что пакет не установлен: {msg}")
                msgs += 0.4
                
            if msgs:
                last_activity = time.time()
                progress_sofar = min(round(progress_sofar + msgs), 95)
                self.update_progress(progress_sofar)
                
            now = time.time()
            if now - last_activity > NO_ACTIVITY_SEC:
                self.update_log("Предупреждение: процесс неактивен, прерываем.")
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
                return False
                
            if now - start > TIMEOUT_SEC:
                self.update_log("Таймаут > 2000 часов, прерываем.")
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
                return False
                
            if QCoreApplication.instance() and QThread.currentThread() == QCoreApplication.instance().thread():
                QApplication.processEvents()
            time.sleep(0.05)
            
        while not q_out.empty():
            self.update_log(q_out.get_nowait())
        while not q_err.empty():
            self.update_log(q_err.get_nowait())
            
        self.update_progress(100)
        ret = proc.returncode
        self.update_log(f"pip завершился с кодом {ret}")
        
        if "uninstall" in cmd and ret in (1, 2):
            logger.info(f"UV вернул код {ret} при удалении - возможно пакет не был установлен")
            return True
        
        return ret == 0