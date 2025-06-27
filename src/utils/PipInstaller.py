"""
PipInstaller 2.0

•  Больше не создаёт собственное tk-окно, если ему передали
   «чужое» progress_window (Qt-диалог или None);
•  Не делает tk-специфичных вызовов, если окно не-Tk;
•  Все callback’и (update_log / update_status / update_progress)
   вызываются в том же потоке, в котором идёт установка.  Для
   нормальной работы в Qt нужно просто вызывать
   QApplication.processEvents() — это уже делается в цикле.
"""

from __future__ import annotations
import subprocess, sys, os, queue, threading, time, json
# import tkinter as tk       # импорт остаётся, чтобы старый путь тоже работал
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, NormalizedName
from packaging.version import parse as parse_version
from Logger import logger


class DependencyResolver:
    def __init__(self, libs_path_abs, update_log_func):
        self.libs_path = libs_path_abs
        self.update_log = update_log_func
        self.cache_file_path = os.path.join(self.libs_path, "dependency_cache.json")
        self._dist_info_cache = {}
        self._dep_cache = {} # Кэш прямых зависимостей для текущего запуска
        self._tree_cache = self._load_tree_cache() # Кэш полных деревьев из файла

    def _get_package_version(self, package_name_canon: NormalizedName) -> str | None:
        dist_info_path = self._find_dist_info_path(package_name_canon)
        if not dist_info_path:
            return None
        # Версия обычно есть в имени папки .dist-info
        # Пример: numpy-1.23.5.dist-info
        try:
            parts = os.path.basename(dist_info_path).split('-')
            if len(parts) >= 2 and parts[-1] == "dist-info":
                version_str = parts[-2]
                # Простая проверка, что это похоже на версию
                if version_str and version_str[0].isdigit():
                    # Нормализуем версию на всякий случай
                    return str(parse_version(version_str))
        except Exception:
            pass # Ошибка парсинга версии

        # Если не нашли в имени, попробуем из METADATA (менее надежно)
        metadata_path = os.path.join(dist_info_path, "METADATA")
        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.lower().startswith("version:"):
                            return line.split(":", 1)[1].strip()
            except Exception:
                pass
        return None

    def _load_tree_cache(self):
        if os.path.exists(self.cache_file_path):
            try:
                with open(self.cache_file_path, 'r', encoding='utf-8') as f:
                    # Простая загрузка, без блокировок, т.к. читаем один раз при инициализации
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                self.update_log(f"Предупреждение: Не удалось загрузить кэш зависимостей: {e}")
        return {}

    def _save_tree_cache(self):
        try:
            # Простая запись, без блокировок, т.к. вызывается редко
            with open(self.cache_file_path, 'w', encoding='utf-8') as f:
                json.dump(self._tree_cache, f, indent=4)
        except IOError as e:
            self.update_log(f"Ошибка сохранения кэша зависимостей: {e}")

    def _find_dist_info_path(self, package_name_canon: NormalizedName):
        if package_name_canon in self._dist_info_cache:
            return self._dist_info_cache[package_name_canon]
        if not os.path.exists(self.libs_path): return None
        for item in os.listdir(self.libs_path):
            if item.endswith(".dist-info"):
                try:
                    dist_name = item.split('-')[0]
                    if canonicalize_name(dist_name) == package_name_canon:
                        path = os.path.join(self.libs_path, item)
                        self._dist_info_cache[package_name_canon] = path
                        return path
                except Exception: continue
        self._dist_info_cache[package_name_canon] = None
        return None

    def _get_direct_dependencies(self, package_name_canon: NormalizedName):
        if package_name_canon in self._dep_cache:
            return self._dep_cache[package_name_canon]
        dependencies = set()
        dist_info_path = self._find_dist_info_path(package_name_canon)
        if not dist_info_path:
            self._dep_cache[package_name_canon] = dependencies
            return dependencies
        metadata_path = os.path.join(dist_info_path, "METADATA")
        if not os.path.exists(metadata_path):
            self._dep_cache[package_name_canon] = dependencies
            return dependencies
        try:
            with open(metadata_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.lower().startswith("requires-dist:"):
                        req_str = line.split(":", 1)[1].strip()
                        try:
                            req_part = req_str.split(';')[0].strip()
                            if req_part: dependencies.add(canonicalize_name(Requirement(req_part).name))
                        except Exception: pass
        except Exception: pass
        self._dep_cache[package_name_canon] = dependencies
        return dependencies

    def get_dependency_tree(self, root_package_name: str) -> set[NormalizedName]:
        root_canon = canonicalize_name(root_package_name)
        installed_version = self._get_package_version(root_canon)

        if not installed_version:
            self.update_log(f"Пакет '{root_package_name}' не найден в Lib, дерево зависимостей не может быть построено.")
            # Удаляем из кэша, если он там был с другой версией
            if root_canon in self._tree_cache:
                del self._tree_cache[root_canon]
                self._save_tree_cache()
            return set()

        # Проверяем кэш
        cached_entry = self._tree_cache.get(root_canon)
        if cached_entry and cached_entry.get("version") == installed_version:
            self.update_log(f"Используется кэшированное дерево зависимостей для {root_canon}=={installed_version}")
            return set(cached_entry.get("dependencies", []))

        # Строим дерево, если кэш неактуален или отсутствует
        self.update_log(f"Построение дерева зависимостей для {root_canon}=={installed_version}...")
        required_set = {root_canon}
        queue = [root_canon]
        processed = set()
        self._dist_info_cache = {} # Сбрасываем кэш путей для нового расчета
        self._dep_cache = {}      # Сбрасываем кэш прямых зависимостей

        while queue:
            current_pkg_canon = queue.pop(0)
            if current_pkg_canon in processed: continue
            processed.add(current_pkg_canon)
            direct_deps = self._get_direct_dependencies(current_pkg_canon)
            for dep_canon in direct_deps:
                if dep_canon not in required_set:
                    required_set.add(dep_canon)
                    if dep_canon not in processed: queue.append(dep_canon)

        # Сохраняем в кэш
        self._tree_cache[root_canon] = {
            "version": installed_version,
            "dependencies": sorted(list(required_set)) # Сохраняем как список для JSON
        }
        self._save_tree_cache()
        self.update_log(f"Дерево зависимостей для {root_canon} построено и закэшировано.")
        return required_set

    def get_all_installed_packages(self) -> set[NormalizedName]:
        installed_set = set()
        if not os.path.exists(self.libs_path): return installed_set
        for item in os.listdir(self.libs_path):
            if item.endswith(".dist-info"):
                try: installed_set.add(canonicalize_name(item.split('-')[0]))
                except Exception: pass
        return installed_set
# ─────────────────────────────────────────────────────────────
#  PipInstaller
# ─────────────────────────────────────────────────────────────
class PipInstaller:
    def __init__(
        self,
        script_path: str,
        libs_path: str = "Lib",
        update_status=None,
        update_log=None,
        progress_window=None,
        update_progress=None
    ):
        self.script_path = script_path
        self.libs_path = libs_path
        self.libs_path_abs = os.path.abspath(libs_path)

        # Callbacks
        self.update_status   = update_status or (lambda m: logger.info(f"STATUS: {m}"))
        self.update_log      = update_log    or (lambda m: logger.info(f"LOG   : {m}"))
        self.update_progress = update_progress or (lambda *_: None)

        self.progress_window = progress_window
        self._ensure_libs_path()

    # ─────────────────────────────────────────────────────────
    #  public helpers
    # ─────────────────────────────────────────────────────────
    def install_package(self, package_spec, description="Установка пакета...", extra_args=None) -> bool:
        self._ensure_libs_path()
        cmd = [self.script_path, "-m", "pip", "install",
               "--target", self.libs_path_abs,
               "--no-user", "--no-cache-dir"]
        if extra_args:
            cmd.extend(extra_args)
        if isinstance(package_spec, list):
            cmd.extend(package_spec)
        else:
            cmd.append(package_spec)
        return self._run_pip_process(cmd, description)

    def uninstall_packages(self, packages: list[str], description="Удаление пакетов...") -> bool:
        if not packages:
            self.update_log("Список пакетов для удаления пуст.")
            return True
        cmd = [self.script_path, "-m", "pip", "uninstall", "--yes"] + packages
        return self._run_pip_process(cmd, description)

    # ─────────────────────────────────────────────────────────
    #  internal
    # ─────────────────────────────────────────────────────────
    def _ensure_libs_path(self):
        if not os.path.exists(self.libs_path):
            os.makedirs(self.libs_path, exist_ok=True)
            self.update_log(f"Создана директория {self.libs_path}")
        if self.libs_path_abs not in sys.path:
            sys.path.insert(0, self.libs_path_abs)

    def _run_pip_process(self, cmd: list[str], description: str) -> bool:
        # определяем, tk-окно ли
        is_tk_window = hasattr(self.progress_window, "winfo_exists") \
                    and callable(self.progress_window.winfo_exists)

        self.update_status(description)
        self.update_log("Выполняем: " + " ".join(cmd))

        self.update_log("[DEBUG] внутри _run_pip_process, сейчас вызовем Popen")
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding="utf-8",
                errors="ignore",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            self.update_log("[DEBUG] Popen запущен, pid=%s" % proc.pid)
        except FileNotFoundError:
            self.update_status("Python не найден")
            self.update_log("ОШИБКА: не найден интерпретатор Python.")
            return False
        except Exception as e:
            self.update_status("Ошибка запуска процесса")
            self.update_log(f"ОШИБКА запуска subprocess: {e}")
            return False

        # неблокирующее чтение
        q_out, q_err = queue.Queue(), queue.Queue()

        def _reader(pipe, q):
            try:
                for line in iter(pipe.readline, ""):
                    q.put(line.rstrip())
            finally:
                pipe.close()

        threading.Thread(target=_reader, args=(proc.stdout, q_out), daemon=True).start()
        threading.Thread(target=_reader, args=(proc.stderr, q_err), daemon=True).start()

        start          = time.time()
        last_activity  = start
        TIMEOUT_SEC    = 7200
        NO_ACTIVITY_SEC = 1800
        progress_sofar = 0            # будем повышать до 95 %

        while proc.poll() is None:
            # окно закрыли (tk-ветка)
            if is_tk_window and not self.progress_window.winfo_exists():
                self.update_log("Окно закрыто, прерываем процесс.")
                proc.terminate(); time.sleep(0.5); proc.kill()
                return False

            # читаем очередные строки
            msgs = 0
            while not q_out.empty():
                self.update_log(q_out.get_nowait())
                msgs += 1
            while not q_err.empty():
                self.update_log(q_err.get_nowait())
                msgs += 1
            if msgs:
                last_activity = time.time()
                # поднимаем прогресс «на глаз»
                progress_sofar = min(progress_sofar + msgs, 95)
                self.update_progress(progress_sofar)

            # таймауты
            now = time.time()
            if now - last_activity > NO_ACTIVITY_SEC:
                self.update_log("Предупреждение: процесс неактивен, прерываем.")
                proc.terminate(); time.sleep(0.5); proc.kill()
                return False
            if now - start > TIMEOUT_SEC:
                self.update_log("Таймаут > 2 ч, прерываем.")
                proc.terminate(); time.sleep(0.5); proc.kill()
                return False

            # обновляем tk-окно
            if is_tk_window and self.progress_window.winfo_exists():
                try:
                    self.progress_window.update()
                except Exception:
                    pass

            # даём Qt «подышать»
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()

            time.sleep(0.05)

        # дочитываем остаток
        while not q_out.empty():
            self.update_log(q_out.get_nowait())
        while not q_err.empty():
            self.update_log(q_err.get_nowait())

        self.update_progress(100)          # финальные 100 %

        ret = proc.returncode
        self.update_log(f"pip завершился с кодом {ret}")
        return ret == 0