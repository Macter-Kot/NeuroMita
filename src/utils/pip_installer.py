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
        """
        UV/pip launcher с TTY-агрегатором:
        - по умолчанию на Windows используем PTY-снапшоты, если установлен pywinpty/winpty (таблички с прогрессом);
          если PTY недоступен — фоллбэк на стандартные пайпы;
        - UV_TTY=1 принудительно включает PTY-режим, UV_TTY=0 — принудительно выключает;
        - в снапшотах показывается валидная ETA (по реальной скорости: из вывода uv или из производной done/time);
        - верхняя полоса прогресса = peak-сумма по задачам; статус содержит (ETA mm:ss) для окна.
        """
        from collections import deque
        import re, select

        def log_progress(line: str):
            clean = line.rstrip("\r\n")
            if not clean:
                return
            try:
                logger.log(15, clean)
            except Exception:
                logger.info(clean)
            self.update_log(clean)

        def snapshot_close():
            try:
                self.update_log("__SNAPSHOT_CLOSE__")
            except Exception:
                pass

        def log_error(line: str):
            clean = line.rstrip("\r\n")
            if not clean:
                return
            logger.error(clean)
            self.update_log(clean)


        class UvProgressAggregator:
            RE_PCT   = re.compile(r'(\d{1,3})\s*%')
            RE_PAIR  = re.compile(
                r'(?P<done>\d+(?:\.\d+)?)\s*(?P<dunit>[KMGTP]?i?B|B)\s*/\s*'
                r'(?P<total>\d+(?:\.\d+)?)\s*(?P<tunit>[KMGTP]?i?B|B)',
                re.IGNORECASE
            )
            RE_SPEED = re.compile(r'(?P<speed>\d+(?:\.\d+)?)\s*(?P<sunit>[KMGTP]?i?B|B)/s', re.IGNORECASE)
            RE_PREP  = re.compile(r'preparing packages\.\.\.\s*KATEX_INLINE_OPEN(\d+)\s*/\s*(\d+)KATEX_INLINE_CLOSE', re.IGNORECASE)
            RE_WHL   = re.compile(r'([A-Za-z0-9_.+-]+-[0-9][^-\\/\s]*?.*?\.whl)', re.IGNORECASE)
            RE_TAR   = re.compile(r'([A-Za-z0-9_.+-]+-.*?\.(?:tar\.gz|zip|bz2|xz))', re.IGNORECASE)
            RE_PATH  = re.compile(r'([A-Za-z]:[^\s]+\.whl|/[^\s]+\.whl)', re.IGNORECASE)
            RE_TOKEN = re.compile(r'^\s*([A-Za-z0-9][A-Za-z0-9_.-]{1,})\b')

            SPIN_CHARS = "⠋⠙⠚⠞⠖⠦⠴⠲⠶⠇⠧⠹⠼"

            def __init__(self):
                self.tasks: dict[str, dict] = {}
                self.completed: dict[str, dict] = {}
                self.peak_done: dict[str, int] = {}
                self.peak_total: dict[str, int] = {}
                self.phase_cur: int | None = None
                self.phase_tot: int | None = None

                self.done_epsilon_ratio = 0.995
                self.stale_to_done_sec  = 4.0
                self.hard_stale_sec     = 15.0

                self.hist_window_sec = 8.0  # окно усреднения для оценки скорости (если uv не пишет её)

            @staticmethod
            def unit_mul(unit: str) -> int:
                u = unit.upper()
                dec = {"B":1,"KB":1000,"MB":1000**2,"GB":1000**3,"TB":1000**4,"PB":1000**5}
                bin_ = {"KIB":1024,"MIB":1024**2,"GIB":1024**3,"TIB":1024**4,"PIB":1024**5}
                return bin_.get(u, dec.get(u, 1))

            @staticmethod
            def fmt_bytes(n: float | int) -> str:
                try:
                    n = float(n)
                except Exception:
                    return "?"
                for unit, mul in (("B",1),("KiB",1024),("MiB",1024**2),("GiB",1024**3),("TiB",1024**4)):
                    if n < mul*1024 or unit=="TiB":
                        return f"{n/mul:.1f} {unit}"
                return f"{n:.1f} B"

            @staticmethod
            def fmt_rate(bps: float | int | None) -> str:
                if not bps:
                    return "-"
                try:
                    bps = float(bps)
                except Exception:
                    return "-"
                for unit, mul in (("B/s",1),("KiB/s",1024),("MiB/s",1024**2),("GiB/s",1024**3)):
                    if bps < mul*1024 or unit=="GiB/s":
                        return f"{bps/mul:.1f} {unit}"
                return f"{bps:.1f} B/s"

            @staticmethod
            def fmt_eta(seconds: float | None) -> str | None:
                if seconds is None or seconds < 0:
                    return None
                seconds = int(seconds)
                m, s = divmod(seconds, 60)
                h, m = divmod(m, 60)
                return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

            @staticmethod
            def bar(pct: int | None, width: int = 22) -> str:
                if pct is None:
                    return "|" + "·"*width + "|"
                fill = max(0, min(width, int(round((pct/100)*width))))
                return "|" + "█"*fill + "_"*(width-fill) + "|"

            @staticmethod
            def clean(s: str) -> str:
                ANSI_RE = re.compile(r'\x1B(?:\[[0-?]*[ -/]*[@-~]|][^ \x07\x1B]*[^ \x07\x1B\\](?:\x1B\\|\x07))')
                if not s:
                    return ""
                return ANSI_RE.sub('', s).replace("\x1b", "")


            @staticmethod
            def canon_name_from_wheel(w: str) -> tuple[str, str]:
                base = w.rsplit("/",1)[-1].rsplit("\\",1)[-1]
                pkg = base.split("-",1)[0]
                return base.lower(), pkg

            def ident_and_display(self, s: str) -> tuple[str, str] | None:
                m = self.RE_WHL.search(s) or self.RE_TAR.search(s) or self.RE_PATH.search(s)
                if m:
                    wheel = m.group(1)
                    cid, disp = self.canon_name_from_wheel(wheel)
                    return cid, disp
                m = self.RE_TOKEN.match(s)
                if m:
                    tok = m.group(1)
                    low = tok.lower()
                    if low in ("preparing","resolving","building","fetching"):
                        return None
                    if tok and (tok[0] in self.SPIN_CHARS or tok in ("i.",":",";",".","…")):
                        return None
                    return low, tok
                return None

            def _ensure_hist(self, t: dict):
                if "hist" not in t:
                    from collections import deque as _dq
                    t["hist"] = _dq(maxlen=120)

            def _push_hist(self, t: dict, ts: float):
                self._ensure_hist(t)
                d = t.get("done")
                if d is None:
                    return
                h = t["hist"]
                if not h or h[-1][1] != d:
                    h.append((ts, int(d)))

                # подчистим старые точки вне окна
                w = self.hist_window_sec
                while len(h) >= 2 and (ts - h[0][0] > max(w*1.5, 2*w)):
                    h.popleft()

            def estimate_speed(self, t: dict) -> float:
                # приоритет: скорость из вывода uv
                sp = t.get("speed_bps")
                if sp and sp > 0:
                    return float(sp)
                # иначе — производная done/time по истории
                h = t.get("hist") or []
                if len(h) < 2:
                    return 0.0
                ts_now = h[-1][0]
                # выбираем самую раннюю точку в окне
                w = self.hist_window_sec
                idx = 0
                for i in range(len(h)-2, -1, -1):
                    if ts_now - h[i][0] > w:
                        idx = i
                        break
                dt = ts_now - h[idx][0]
                if dt <= 0:
                    return 0.0
                dd = float(h[-1][1] - h[idx][1])
                if dd <= 0:
                    return 0.0
                return dd / dt

            def update(self, raw_line: str):
                s = self.clean(raw_line).strip()
                if not s:
                    return

                mp = self.RE_PREP.search(s)
                if mp:
                    try:
                        self.phase_cur = int(mp.group(1))
                        self.phase_tot = int(mp.group(2))
                    except Exception:
                        pass
                    return

                ident_disp = self.ident_and_display(s)
                if not ident_disp:
                    return
                cid, disp = ident_disp

                t = self.tasks.get(cid)
                if not t:
                    t = {
                        "id": cid, "name": disp, "pct": None,
                        "done": None, "total": None,
                        "speed_bps": None, "eta": None, "ts": time.time()
                    }
                    self.tasks[cid] = t

                m = self.RE_PCT.search(s)
                if m:
                    try:
                        t["pct"] = max(0, min(100, int(m.group(1))))
                    except Exception:
                        pass

                m = self.RE_PAIR.search(s)
                if m:
                    try:
                        d = float(m.group("done"))  * self.unit_mul(m.group("dunit"))
                        T = float(m.group("total")) * self.unit_mul(m.group("tunit"))
                        t["done"], t["total"] = int(d), int(T)
                        if T > 0:
                            t["pct"] = max(0, min(100, int(round(d/T*100))))
                    except Exception:
                        pass

                m = self.RE_SPEED.search(s)
                if m:
                    try:
                        sp = float(m.group("speed")) * self.unit_mul(m.group("sunit"))
                        t["speed_bps"] = sp
                    except Exception:
                        t["speed_bps"] = None

                # обновим историю и оценим ETA
                now = time.time()
                if t.get("done") is not None:
                    self._push_hist(t, now)

                if t.get("done") is not None and t.get("total") is not None:
                    rem = max(0.0, float(t["total"] - t["done"]))
                    sp_est = self.estimate_speed(t)
                    t["eta"] = self.fmt_eta(rem/sp_est if sp_est > 0 else None)
                else:
                    t["eta"] = None

                self._record_peaks(t)
                t["ts"] = now

            def _record_peaks(self, t: dict):
                cid = t["id"]
                if t.get("total") is not None:
                    self.peak_total[cid] = max(self.peak_total.get(cid, 0), int(t["total"]))
                if t.get("done") is not None:
                    peak_T = self.peak_total.get(cid, int(t.get("done", 0)))
                    self.peak_done[cid] = max(self.peak_done.get(cid, 0), min(int(t.get("done", 0)), peak_T))

            def prune(self, now: float):
                to_close = []
                for cid, t in list(self.tasks.items()):
                    pct = t.get("pct")
                    done, total = t.get("done"), t.get("total")
                    ratio = (float(done)/float(total)) if (done is not None and total) else None
                    if (pct is not None and pct >= 99) or (ratio is not None and ratio >= self.done_epsilon_ratio):
                        to_close.append(cid)
                        continue
                    idle = now - t["ts"]
                    if ratio is not None and ratio >= 0.95 and idle >= self.stale_to_done_sec:
                        to_close.append(cid)
                        continue
                    if idle >= self.hard_stale_sec:
                        to_close.append(cid)

                for cid in to_close:
                    t = self.tasks.pop(cid, None)
                    if t:
                        self._record_peaks(t)
                        self.completed[cid] = t

            def overall_percent(self) -> int | None:
                if not self.peak_total:
                    return None
                total_total = sum(self.peak_total.values())
                if total_total <= 0:
                    return None
                total_done = 0
                for cid, T in self.peak_total.items():
                    d = min(self.peak_done.get(cid, 0), T)
                    total_done += d
                return int(max(0, min(100, round(total_done / total_total * 100))))

            def overall_eta_bytes(self) -> float | None:
                # ETA по суммарной скорости всех активных задач
                items = list(self.tasks.values())
                sum_total = 0.0
                sum_done  = 0.0
                sum_speed = 0.0
                for t in items:
                    T = t.get("total"); d = t.get("done")
                    if T is None or d is None:
                        continue
                    sum_total += float(T); sum_done += float(d)
                    sp = self.estimate_speed(t)
                    if sp > 0:
                        sum_speed += sp
                if sum_total <= 0 or sum_speed <= 0:
                    return None
                remaining = max(0.0, sum_total - sum_done)
                if remaining <= 0:
                    return 0.0
                return remaining / sum_speed

            def snapshot_lines(self, max_lines: int = 8) -> list[str]:
                lines = []
                if self.phase_cur is not None and self.phase_tot is not None:
                    lines.append(f"Подготовка пакетов: {self.phase_cur}/{self.phase_tot}")

                if not self.tasks:
                    return lines

                items = sorted(self.tasks.values(), key=lambda x: (-x["ts"], x["name"]))

                sum_done = sum((t.get("done") or 0) for t in items if t.get("total"))
                sum_total = sum((t.get("total") or 0) for t in items if t.get("total"))
                pcts = [t["pct"] for t in items if t.get("pct") is not None]
                avg = int(round(sum(pcts)/len(pcts))) if pcts else 0

                sum_line = f"Активных задач: {len(items)}  Средний прогресс: {avg}%"
                if sum_total > 0:
                    sum_line += f"  Σ {self.fmt_bytes(sum_done)}/{self.fmt_bytes(sum_total)}"
                    # скорость и ETA — по оценочной скорости (вычисляем даже если uv её не пишет)
                    sum_speed = sum(self.estimate_speed(t) for t in items)
                    if sum_speed > 0:
                        eta_sec = (sum_total - sum_done)/sum_speed if sum_total>sum_done else 0.0
                        eta_txt = self.fmt_eta(eta_sec)
                        if eta_txt:
                            sum_line += f"  Σскорость: {self.fmt_rate(sum_speed)}  ETA: {eta_txt}"
                lines.append(sum_line)

                count = 0
                for t in items:
                    name = t["name"]
                    if len(name) > 28:
                        name = name[:25]+"..."
                    bar  = self.bar(t.get("pct"))
                    right = []
                    if t.get("pct") is not None:
                        right.append(f"{t['pct']:3d}%")
                    if t.get("done") is not None and t.get("total") is not None:
                        right.append(f"{self.fmt_bytes(t['done'])}/{self.fmt_bytes(t['total'])}")
                    sp_est = self.estimate_speed(t)
                    if sp_est > 0:
                        right.append(self.fmt_rate(sp_est))
                    if t.get("eta"):
                        right.append(f"ETA {t['eta']}")
                    r = "  " + "  ".join(right) if right else ""
                    lines.append(f"{name:28} {bar}{r}")
                    count += 1
                    if count >= max_lines:
                        break
                return lines

        snapshot_close()

        # запуск
        self.update_status(description)
        self.update_log("Выполняем: " + " ".join(cmd))

        env = os.environ.copy()
        env.setdefault("PIP_PROGRESS_BAR", "on")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("NO_COLOR", "1")
        env.setdefault("CLICOLOR", "0")
        env.setdefault("FORCE_COLOR", "0")
        env.setdefault("PY_COLORS", "0")
        env.setdefault("TERM", "dumb")

        is_windows = os.name == "nt"

        # Выбор PTY по умолчанию:
        # - если UV_TTY=1 — принудительно включаем;
        # - если UV_TTY=0 — принудительно выключаем;
        # - иначе на Windows включаем ТОЛЬКО если доступен pywinpty/winpty; на POSIX — по умолчанию выключено.
        uv_tty_env = os.environ.get("UV_TTY")
        windows_pty_available = False
        PtyProcess = None

        if is_windows:
            try:
                from pywinpty import PtyProcess as _PtyProcess
                PtyProcess = _PtyProcess
                windows_pty_available = True
            except Exception:
                try:
                    import winpty  # type: ignore
                    PtyProcess = winpty.PtyProcess  # type: ignore
                    windows_pty_available = True
                except Exception:
                    windows_pty_available = False

        if uv_tty_env == "1":
            use_pty = True
        elif uv_tty_env == "0":
            use_pty = False
        else:
            use_pty = (windows_pty_available if is_windows else False)

        start = time.time()
        last_activity = start
        last_status_emit = start
        last_status_message = None

        STALL_INFO_SEC = 10
        STALL_HINT_SEC = 60
        TIMEOUT_SEC = 7200000
        NO_ACTIVITY_SEC = 3600000

        from collections import deque as _deque
        progress_sofar = 0
        progress_history = _deque(maxlen=60)
        progress_history.append((start, 0))

        cmd_str = " ".join(cmd).lower()
        is_pytorch_install = ("download.pytorch.org" in cmd_str) or ("torch" in cmd_str and "install" in cmd_str)
        torch_hint_logged = False
        error_kw = ("error", "ошибка", "failed", "traceback", "exception", "critical")

        # ======== PTY PATH ========
        if use_pty:
            try:
                agg = UvProgressAggregator()
                last_snapshot_emit = time.time()

                if not is_windows:
                    import pty, fcntl, os as _os
                    master_fd, slave_fd = pty.openpty()
                    fl = fcntl.fcntl(master_fd, fcntl.F_GETFL)
                    fcntl.fcntl(master_fd, fcntl.F_SETFL, fl | _os.O_NONBLOCK)

                    proc = subprocess.Popen(cmd, stdin=slave_fd, stdout=slave_fd, stderr=slave_fd, env=env, close_fds=True)
                    _os.close(slave_fd)

                    buffer = ""
                    while proc.poll() is None:
                        rlist, _, _ = select.select([master_fd], [], [], 0.05)
                        if master_fd in rlist:
                            try:
                                chunk = _os.read(master_fd, 8192).decode("utf-8", errors="ignore")
                            except BlockingIOError:
                                chunk = ""
                            if chunk:
                                buffer += chunk
                                parts = re.split(r'(\r|\n)', buffer)
                                buffer = ""
                                line_acc = ""
                                i = 0
                                while i < len(parts):
                                    token = parts[i]
                                    if token == "\n":
                                        line = line_acc.strip()
                                        if line:
                                            if any(k in line.lower() for k in error_kw):
                                                log_error(UvProgressAggregator.clean(line))
                                            else:
                                                agg.update(line)
                                            last_activity = time.time()
                                            # для плавности верхней полосы
                                            progress_sofar = min(progress_sofar + 1, 95)
                                            self.update_progress(progress_sofar)
                                            progress_history.append((last_activity, progress_sofar))
                                        line_acc = ""
                                    elif token == "\r":
                                        line = line_acc.strip()
                                        if line:
                                            if any(k in line.lower() for k in error_kw):
                                                log_error(UvProgressAggregator.clean(line))
                                            else:
                                                agg.update(line)
                                            self.update_status(f"{description} — {UvProgressAggregator.clean(line)}")
                                        line_acc = ""
                                    else:
                                        line_acc += token
                                    i += 1
                                buffer = line_acc

                        now = time.time()
                        agg.prune(now)

                        if now - last_snapshot_emit >= 0.1:
                            snap = agg.snapshot_lines()
                            if snap:
                                self.update_log("__SNAPSHOT_START__\n" + "\n".join(snap) + "\n__SNAPSHOT_END__")
                            pct = agg.overall_percent()
                            if pct is not None:
                                self.update_progress(min(99, max(3, pct)))
                                progress_sofar = max(progress_sofar, pct)
                            last_snapshot_emit = now

                        if now - last_status_emit >= 0.5:
                            # предпочитаем ETA по байтам и скорости; иначе — по тренду процента
                            eta_secs = agg.overall_eta_bytes()
                            if eta_secs is None and progress_sofar >= 3 and len(progress_history) >= 2:
                                t0, p0 = progress_history[0]
                                dt, dp = now - t0, progress_sofar - p0
                                if dt > 0 and dp > 0:
                                    eta_secs = int(max(0.0, (100.0 - progress_sofar)) / (dp/dt))
                            msg = f"{description} — {progress_sofar}%"
                            if eta_secs is not None:
                                if isinstance(eta_secs, float):
                                    eta_secs = int(eta_secs)
                                m, s = divmod(int(eta_secs), 60)
                                msg += f" (ETA {m:02d}:{s:02d})"
                            if msg != last_status_message:
                                self.update_status(msg)
                                last_status_message = msg
                            last_status_emit = now

                            if is_pytorch_install and not torch_hint_logged and (now - last_activity) >= STALL_HINT_SEC:
                                self.update_log("Похоже, идёт загрузка больших бинарников PyTorch. Это может долго не писать прогресс.")
                                torch_hint_logged = True

                        if now - last_activity > NO_ACTIVITY_SEC:
                            log_error("Процесс неактивен слишком долго, прерываем.")
                            self.update_status(description + " — прервано по таймауту неактивности.")
                            proc.terminate()
                            time.sleep(0.5)
                            if proc.poll() is None:
                                proc.kill()
                            snapshot_close()
                            return False

                        if now - start > TIMEOUT_SEC:
                            log_error("Таймаут процесса истёк, прерываем.")
                            self.update_status(description + " — прервано по общему таймауту.")
                            proc.terminate()
                            time.sleep(0.5)
                            if proc.poll() is None:
                                proc.kill()
                            snapshot_close()
                            return False

                        if QCoreApplication.instance() and QThread.currentThread() == QCoreApplication.instance().thread():
                            QApplication.processEvents()

                    snap = agg.snapshot_lines()
                    if snap:
                        self.update_log("__SNAPSHOT_START__\n" + "\n".join(snap) + "\n__SNAPSHOT_END__")

                    ret = proc.returncode
                    self.update_progress(100)

                    snapshot_close()

                    self.update_log(f"pip завершился с кодом {ret}")
                    elapsed = time.time() - start
                    self.update_status(f"{description} — завершено за {int(elapsed//60):02d}:{int(elapsed%60):02d}")

                    if "uninstall" in cmd and ret in (1, 2):
                        logger.info(f"UV вернул код {ret} при удалении - возможно пакет не был установлен")
                        return True
                    if ret != 0:
                        logger.error(f"pip завершился с ошибкой, код {ret}")
                        return False
                    return True

                else:
                    # Windows + winpty/pywinpty
                    if PtyProcess is None:
                        # нет winpty — фоллбэк на пайпы
                        raise RuntimeError("winpty/pywinpty недоступен")

                    try:
                        cmdline = subprocess.list2cmdline(cmd)
                    except Exception:
                        import shlex
                        cmdline = " ".join(shlex.quote(c) if " " in c else c for c in cmd)

                    pty = PtyProcess.spawn(cmdline)
                    buffer, line_acc = "", ""
                    error_seen = False
                    last_snapshot_emit = time.time()

                    while pty.isalive():
                        try:
                            chunk = pty.read(8192)
                        except Exception:
                            chunk = ""

                        if chunk:
                            if isinstance(chunk, bytes):
                                try:
                                    chunk = chunk.decode("utf-8", errors="ignore")
                                except Exception:
                                    chunk = chunk.decode("cp1251", errors="ignore")

                            buffer += chunk
                            parts = re.split(r'(\r|\n)', buffer)
                            buffer = ""
                            i = 0
                            while i < len(parts):
                                token = parts[i]
                                if token == "\n":
                                    full = line_acc.strip()
                                    if full:
                                        if any(k in full.lower() for k in error_kw):
                                            log_error(UvProgressAggregator.clean(full)); error_seen = True
                                        else:
                                            agg.update(full)
                                        last_activity = time.time()
                                        progress_sofar = min(progress_sofar + 1, 95)
                                        self.update_progress(progress_sofar)
                                        progress_history.append((last_activity, progress_sofar))
                                    line_acc = ""
                                elif token == "\r":
                                    status_line = line_acc.strip()
                                    if status_line:
                                        if any(k in status_line.lower() for k in error_kw):
                                            log_error(UvProgressAggregator.clean(status_line)); error_seen = True
                                        else:
                                            agg.update(status_line)
                                        self.update_status(f"{description} — {UvProgressAggregator.clean(status_line)}")
                                    line_acc = ""
                                else:
                                    line_acc += token
                                i += 1

                        now = time.time()
                        agg.prune(now)

                        if now - last_snapshot_emit >= 0.1:
                            snap = agg.snapshot_lines()
                            if snap:
                                self.update_log("__SNAPSHOT_START__\n" + "\n".join(snap) + "\n__SNAPSHOT_END__")
                            pct = agg.overall_percent()
                            if pct is not None:
                                self.update_progress(min(99, max(3, pct)))
                                progress_sofar = max(progress_sofar, pct)
                            last_snapshot_emit = now

                        if now - last_status_emit >= 0.5:
                            eta_secs = agg.overall_eta_bytes()
                            if eta_secs is None and progress_sofar >= 3 and len(progress_history) >= 2:
                                t0, p0 = progress_history[0]
                                dt, dp = now - t0, progress_sofar - p0
                                if dt > 0 and dp > 0:
                                    eta_secs = int(max(0.0, (100.0 - progress_sofar)) / (dp/dt))
                            msg = f"{description} — {progress_sofar}%"
                            if eta_secs is not None:
                                if isinstance(eta_secs, float):
                                    eta_secs = int(eta_secs)
                                m, s = divmod(int(eta_secs), 60)
                                msg += f" (ETA {m:02d}:{s:02d})"
                            if msg != last_status_message:
                                self.update_status(msg)
                                last_status_message = msg
                            last_status_emit = now

                            if is_pytorch_install and not torch_hint_logged and (now - last_activity) >= STALL_HINT_SEC:
                                self.update_log("Похоже, идёт загрузка больших бинарников PyTorch. Пожалуйста, подождите.")
                                torch_hint_logged = True

                        if QCoreApplication.instance() and QThread.currentThread() == QCoreApplication.instance().thread():
                            QApplication.processEvents()
                        time.sleep(0.05)

                    snap = agg.snapshot_lines()
                    if snap:
                        self.update_log("__SNAPSHOT_START__\n" + "\n".join(snap) + "\n__SNAPSHOT_END__")

                    ret = pty.exitstatus
                    self.update_progress(100)

                    snapshot_close()

                    self.update_log(f"pip завершился с кодом {ret}")
                    elapsed = time.time() - start
                    self.update_status(f"{description} — завершено за {int(elapsed//60):02d}:{int(elapsed%60):02d}")


                    if "uninstall" in cmd and ret in (1, 2):
                        logger.info(f"UV вернул код {ret} при удалении - возможно пакет не был установлен")
                        return True
                    if ret != 0:
                        if not error_seen:
                            log_error(f"Команда завершилась с ошибкой, код {ret}. Проверьте строки выше.")
                        logger.error(f"pip завершился с ошибкой, код {ret}")
                        return False
                    return True

            except Exception as e:
                logger.warning(f"PTY-режим недоступен или произошла ошибка: {e}. Переходим на стандартные пайпы.", exc_info=True)
                snapshot_close()
                # фоллбэк на пайпы ниже

        # ======== PIPES PATH ========
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
            log_error("ОШИБКА: не найден интерпретатор Python.")
            self.update_status(description + " — ошибка.")
            return False
        except Exception as e:
            log_error(f"ОШИБКА запуска subprocess: {e}")
            self.update_status(description + " — ошибка.")
            return False

        q_out, q_err = queue.Queue(), queue.Queue()

        def _reader(pipe, q):
            try:
                for line in iter(pipe.readline, ""):
                    q.put(line.rstrip())
            finally:
                try:
                    pipe.close()
                except Exception:
                    pass

        threading.Thread(target=_reader, args=(proc.stdout, q_out), daemon=True).start()
        threading.Thread(target=_reader, args=(proc.stderr, q_err), daemon=True).start()

        while proc.poll() is None:
            msgs = 0.0
            while not q_out.empty():
                line = q_out.get_nowait()
                if line:
                    if any(k in line.lower() for k in error_kw):
                        log_error(line)
                    else:
                        log_progress(line)
                    msgs += 0.4
            while not q_err.empty():
                msg = q_err.get_nowait()
                if msg:
                    if any(k in msg.lower() for k in error_kw):
                        log_error(msg)
                    else:
                        log_progress(msg)
                    msgs += 0.4

            if msgs:
                last_activity = time.time()
                progress_sofar = min(round(progress_sofar + msgs), 95)
                self.update_progress(progress_sofar)

            now = time.time()
            if now - last_status_emit >= 0.5:
                eta_i = None
                if progress_sofar >= 3 and len(progress_history) >= 2:
                    t0, p0 = progress_history[0]
                    dt, dp = now - t0, progress_sofar - p0
                    if dt > 0 and dp > 0:
                        eta_i = int(max(0.0, (100.0 - progress_sofar)) / (dp/dt))
                stalled_sec = int(now - last_activity)
                msg = f"{description} — {progress_sofar}%"
                if eta_i is not None:
                    m, s = divmod(int(eta_i), 60)
                    msg += f" (ETA {m:02d}:{s:02d})"
                elif stalled_sec >= STALL_INFO_SEC:
                    msg += f" (нет вывода {stalled_sec} с, процесс работает)"
                if msg != last_status_message:
                    self.update_status(msg)
                    last_status_message = msg
                last_status_emit = now

                if is_pytorch_install and stalled_sec >= STALL_HINT_SEC and not torch_hint_logged:
                    self.update_log("Похоже, идёт загрузка больших бинарников PyTorch с pytorch.org. Это может долго не писать прогресс.")
                    torch_hint_logged = True

            if now - last_activity > NO_ACTIVITY_SEC:
                log_error("Процесс неактивен слишком долго, прерываем.")
                self.update_status(description + " — прервано по таймауту неактивности.")
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
                snapshot_close()
                return False

            if now - start > TIMEOUT_SEC:
                log_error("Таймаут процесса истёк, прерываем.")
                self.update_status(description + " — прервано по общему таймауту.")
                proc.terminate()
                time.sleep(0.5)
                if proc.poll() is None:
                    proc.kill()
                snapshot_close()
                return False

            if QCoreApplication.instance() and QThread.currentThread() == QCoreApplication.instance().thread():
                QApplication.processEvents()
            time.sleep(0.05)

        while not q_out.empty():
            ln = q_out.get_nowait()
            if any(k in ln.lower() for k in error_kw):
                log_error(ln)
            else:
                log_progress(ln)
        while not q_err.empty():
            ln = q_err.get_nowait()
            if any(k in ln.lower() for k in error_kw):
                log_error(ln)
            else:
                log_progress(ln)

        
        ret = proc.returncode
        self.update_progress(100)

        snapshot_close()

        self.update_log(f"pip завершился с кодом {ret}")
        elapsed = time.time() - start
        self.update_status(f"{description} — завершено за {int(elapsed//60):02d}:{int(elapsed%60):02d}")

        if "uninstall" in cmd and ret in (1, 2):
            logger.info(f"UV вернул код {ret} при удалении - возможно пакет не был установлен")
            return True
        if ret != 0:
            logger.error(f"pip завершился с ошибкой, код {ret}")
            return False
        return True
