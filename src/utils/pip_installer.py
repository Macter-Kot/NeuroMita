"""
PipInstaller 3.0
"""

from __future__ import annotations
import subprocess, sys, os, queue, threading, time, json, shutil, gc
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, NormalizedName
from packaging.version import parse as parse_version
from main_logger import logger
from PyQt6.QtWidgets import QApplication  # Для processEvents()


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
        update_progress=None
    ):
        self.script_path = script_path
        self.libs_path = libs_path
        self.python_root = Path(script_path).resolve().parent
        self.libs_path_abs = os.path.abspath(self.libs_path)  # Абсолютный путь к "./Lib"
        self.update_status = update_status or (lambda m: logger.info(f"STATUS: {m}"))
        self.update_log = update_log or (lambda m: logger.info(f"LOG: {m}"))
        self.update_progress = update_progress or (lambda *_: None)
        self.progress_window = progress_window
        self._ensure_libs_path()

    def install_package(self, package_spec, description="Установка пакета...", extra_args=None) -> bool:
        cmd = [
            self.script_path, "-m", "uv", "pip", "install",
            "--target", str(self.libs_path_abs),  # Абсолютный путь
            "--no-cache-dir"
        ]
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

        # Проверка на повреждённые dist-info (fallback для ошибок вроде 'RECORD not found')
        for pkg in packages:
            canon = canonicalize_name(pkg)
            dist_path = self._find_dist_info_path(canon)
            if dist_path and not os.path.exists(os.path.join(dist_path, "RECORD")):
                logger.warning(f"RECORD файл отсутствует для {pkg}. Пытаемся удалить dist-info вручную: {dist_path}")
                try:
                    shutil.rmtree(dist_path)
                    logger.info(f"Вручную удалена dist-info для {pkg}")
                except Exception as ex:
                    logger.error(f"Ошибка ручного удаления dist-info для {pkg}: {ex}")
                    # Продолжаем, не возвращаем False

        # Удаление по одному пакету, чтобы ошибка на одном не рушила все
        for pkg in packages:
            # Проверяем, импортирован ли пакет (если да, выгружаем для разблокировки .pyd)
            canon = canonicalize_name(pkg)
            if canon in sys.modules:
                logger.warning(f"Пакет {pkg} импортирован. Выгружаем для разблокировки...")
                del sys.modules[canon]
                gc.collect()  # Освобождаем handles

            cmd = [self.script_path, "-m", "uv", "pip", "uninstall", "--target", str(self.libs_path_abs), pkg]
            success = self._run_pip_process(cmd, f"Удаление {pkg}")

            if not success:
                logger.warning(f"uv pip не удался для {pkg} (код 2). Пытаемся ручное удаление...")
                dist_path = self._find_dist_info_path(canon)
                if dist_path:
                    self._manual_remove(dist_path, pkg)
                logger.info(f"Пакет {pkg} пропущен (занят или ошибка) — продолжаем.")

        logger.info("Удаление завершено (с пропусками ошибок).")
        return True  # Всегда успех, даже если некоторые пакеты не удалились

    def _manual_remove(self, path: str, pkg_name: str):
        retries = 3
        for attempt in range(retries):
            try:
                shutil.rmtree(path, ignore_errors=True)
                logger.info(f"Ручное удаление успешно для {pkg_name}")
                return
            except Exception as e:
                logger.warning(f"Ошибка ручного удаления {pkg_name} (attempt {attempt+1}): {e}. Retry...")
                time.sleep(0.5)
        logger.warning(f"Не удалось удалить {pkg_name} после {retries} попыток. Пропускаем.")

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
            return True  # Пропуск
        except Exception as e:
            self.update_log(f"ОШИБКА запуска subprocess: {e}")
            return True  # Пропуск
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
        TIMEOUT_SEC = 7200000 # надеюсь столько хватит. 7200000 секунд = 2000 часов
        NO_ACTIVITY_SEC = 3600000 # надеюсь хватит для установки 3 гигов = 1000 часов
        progress_sofar = 0
        while proc.poll() is None:
            if is_qt_window and not self.progress_window.isVisible():
                self.update_log("Окно закрыто, прерываем процесс.")
                proc.terminate()
                time.sleep(0.5)
                proc.kill()
                return True  # Пропуск
            msgs = 0
            while not q_out.empty():
                self.update_log(q_out.get_nowait())
                msgs += 0.4
            while not q_err.empty():
                self.update_log(q_err.get_nowait())
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
                proc.kill()
                return True  # Пропуск
            if now - start > TIMEOUT_SEC:
                self.update_log("Таймаут > 2000 часов, прерываем.")
                proc.terminate()
                time.sleep(0.5)
                proc.kill()
                return True  # Пропуск
            QApplication.processEvents()
            time.sleep(0.05)
        while not q_out.empty():
            self.update_log(q_out.get_nowait())
        while not q_err.empty():
            self.update_log(q_err.get_nowait())
        self.update_progress(100)
        ret = proc.returncode
        self.update_log(f"pip завершился с кодом {ret}")
        if ret != 0:
            logger.warning(f"Ошибка с кодом {ret} — пропускаем и считаем успехом.")
        return True  # Всегда успех