"""
PipInstaller 3.0
"""

from __future__ import annotations
import subprocess, sys, os, queue, threading, time, json
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, NormalizedName
from packaging.version import parse as parse_version
from Logger import logger


class DependencyResolver:
    def __init__(self, libs_path_abs, update_log_func):
        python_root = Path(sys.executable).resolve().parent
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
            except Exception:
                pass
        return {}

    def _save_tree_cache(self):
        try:
            with open(self.cache_file_path, "w", encoding="utf-8") as f:
                json.dump(self._tree_cache, f, indent=4)
        except Exception:
            pass

    def _find_dist_info_path(self, package_name_canon: NormalizedName):
        cached = self._dist_info_cache.get(package_name_canon)
        if cached is not None:
            return cached
        if not os.path.exists(self.libs_path):
            self._dist_info_cache[package_name_canon] = None
            return None
        for item in os.listdir(self.libs_path):
            if item.endswith(".dist-info"):
                try:
                    dist_name = item.split("-")[0]
                    if canonicalize_name(dist_name) == package_name_canon:
                        p = os.path.join(self.libs_path, item)
                        self._dist_info_cache[package_name_canon] = p
                        return p
                except Exception:
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
        except Exception:
            pass
        meta = os.path.join(dist_path, "METADATA")
        if os.path.exists(meta):
            try:
                with open(meta, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.lower().startswith("version:"):
                            return line.split(":", 1)[1].strip()
            except Exception:
                pass
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
                                except Exception:
                                    pass
                except Exception:
                    pass
        self._dep_cache[package_name_canon] = deps
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
        return required

    def get_all_installed_packages(self):
        pkgs = set()
        if os.path.exists(self.libs_path):
            for item in os.listdir(self.libs_path):
                if item.endswith(".dist-info"):
                    try:
                        pkgs.add(canonicalize_name(item.split("-")[0]))
                    except Exception:
                        pass
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
        self.libs_path_abs = (self.python_root / "Lib" / "site-packages").resolve()
        self.update_status = update_status or (lambda m: logger.info(f"STATUS: {m}"))
        self.update_log = update_log or (lambda m: logger.info(f"LOG   : {m}"))
        self.update_progress = update_progress or (lambda *_: None)
        self.progress_window = progress_window
        self._ensure_libs_path()

    def install_package(self, package_spec, description="Установка пакета...", extra_args=None) -> bool:
        
        lock_path = os.path.join(os.path.dirname(sys.executable), "requirements.lock")
        cmd = [
            self.script_path, "-m", "uv", "pip", "install",
            "--target", self.libs_path,
            "--cache-dir", str(self.python_root.parent / ".cache" / "pip")
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
        cmd = [self.script_path, "-m", "uv", "pip", "uninstall", "--yes"] + packages
        return self._run_pip_process(cmd, description)

    def _ensure_libs_path(self):
        os.makedirs(self.libs_path_abs, exist_ok=True)
        if str(self.libs_path_abs) not in sys.path:
            sys.path.insert(0, str(self.libs_path_abs))

    def _run_pip_process(self, cmd: list[str], description: str) -> bool:
        is_tk_window = hasattr(self.progress_window, "winfo_exists") and callable(self.progress_window.winfo_exists)
        self.update_status(description)
        self.update_log("Выполняем: " + " ".join(cmd))
        env = os.environ.copy()
        env["PIP_CACHE_DIR"] = str(self.python_root.parent / ".cache" / "pip")
        env["UV_CACHE_DIR"] = str(self.python_root.parent / ".cache" / "uv")
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
            self.update_status("Python не найден")
            self.update_log("ОШИБКА: не найден интерпретатор Python.")
            return False
        except Exception as e:
            self.update_status("Ошибка запуска процесса")
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
        TIMEOUT_SEC = 7200
        NO_ACTIVITY_SEC = 3600
        progress_sofar = 0
        while proc.poll() is None:
            if is_tk_window and not self.progress_window.winfo_exists():
                self.update_log("Окно закрыто, прерываем процесс.")
                proc.terminate()
                time.sleep(0.5)
                proc.kill()
                return False
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
                return False
            if now - start > TIMEOUT_SEC:
                self.update_log("Таймаут > 2 ч, прерываем.")
                proc.terminate()
                time.sleep(0.5)
                proc.kill()
                return False
            if is_tk_window and self.progress_window.winfo_exists():
                try:
                    self.progress_window.update()
                except Exception:
                    pass
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            time.sleep(0.05)
        while not q_out.empty():
            self.update_log(q_out.get_nowait())
        while not q_err.empty():
            self.update_log(q_err.get_nowait())
        self.update_progress(100)
        ret = proc.returncode
        self.update_log(f"pip завершился с кодом {ret}")
        return ret == 0