import os
import sys
import importlib
import traceback
import hashlib
from datetime import datetime
import asyncio

from .base_model import IVoiceModel
from typing import Optional, Any, List, Dict
from main_logger import logger

from managers.settings_manager import SettingsManager
from utils import getTranslationVariant as _, get_character_voice_paths

from core.events import get_event_bus, Events


import math, os, time

import requests
import math
from PyQt6.QtCore import QTimer
from utils.pip_installer import PipInstaller

class F5TTSModel(IVoiceModel):
    def __init__(self, parent: 'LocalVoice', model_id: str, rvc_handler: Optional[IVoiceModel] = None):
        super().__init__(parent, model_id)
        self.f5_pipeline_module = None
        self.current_f5_pipeline = None
        self.events = get_event_bus()
        self.rvc_handler = rvc_handler
        self.ruaccent_instance = None

    MODEL_CONFIGS = [
        {
            "id": "high",
            "name": "F5-TTS",
            "min_vram": 4, "rec_vram": 8,
            "gpu_vendor": ["NVIDIA"],
            "size_gb": 4,
            "languages": ["Russian", "English"],
            "intents": [_("Эмоции", "Emotion"), _("Качество", "Quality")],
            "description": _(
                "Эмоциональная диффузионная модель с высоким качеством. Самая требовательная к GPU.",
                "Emotional diffusion model with high quality. Most GPU‑demanding."
            ),
            "settings": [
                {"key": "speed", "label": _("Скорость речи", "Speech Speed"), "type": "entry", "options": {"default": "1.0"},
                "help": _("Множитель скорости: 1.0 — нормальная.", "Speed multiplier: 1.0 is normal.")},
                {"key": "nfe_step", "label": _("Шаги диффузии", "Diffusion Steps"), "type": "entry", "options": {"default": "32"},
                "help": _("Больше шагов — лучше качество, медленнее.", "More steps — better quality, slower.")},
                {"key": "remove_silence", "label": _("Удалять тишину", "Remove Silence"), "type": "checkbutton", "options": {"default": True},
                "help": _("Обрезать тишину в начале/конце.", "Trim silence at head/tail.")},
                {"key": "seed", "label": _("Seed", "Seed"), "type": "entry", "options": {"default": "0"},
                "help": _("Инициализация генератора случайности.", "Random seed.")},
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"},
                "help": _("Итоговая громкость.", "Final loudness.")},
                {"key": "use_ruaccent", "label": _("Использовать RUAccent", "Use RUAccent"), "type": "checkbutton", "options": {"default": False},
                "help": _("Улучшение ударений для русского.", "Better Russian stress handling.")}
            ]
        },
        {
            "id": "high+low",
            "name": "F5-TTS + RVC",
            "min_vram": 6, "rec_vram": 8,
            "gpu_vendor": ["NVIDIA"],
            "size_gb": 7,
            "languages": ["Russian", "English"],
            "intents": [_("Эмоции", "Emotion"), _("Конверсия голоса", "Voice conversion")],
            "description": _(
                "F5‑TTS с последующей конверсией тембра через RVC.",
                "F5‑TTS followed by timbre conversion via RVC."
            ),
            "settings": [
                {"key": "f5rvc_f5_device", "label": _("[F5] Устройство", "[F5] Device"), "type": "combobox",
                "options": {"values": ["cuda", "cpu"], "default": "cuda"},
                "help": _("Устройство для части F5‑TTS.", "Device for F5‑TTS part.")},
                {"key": "f5rvc_rvc_device", "label": _("[RVC] Устройство RVC", "[RVC] RVC Device"), "type": "combobox",
                "options": { "values_nvidia": ["dml", "cuda:0", "cpu"], "default_nvidia": "cuda:0",
                            "values_amd": ["dml", "cpu"], "default_amd": "dml",
                            "values_other": ["cpu", "dml"], "default_other": "cpu" },
                "help": _("Устройство для части RVC.", "Device for RVC part.")},

                {"key": "f5rvc_f5_speed", "label": _("[F5] Скорость речи", "[F5] Speech Speed"), "type": "entry", "options": {"default": "1.0"},
                "help": _("Множитель скорости F5‑TTS.", "F5‑TTS speed multiplier.")},
                {"key": "f5rvc_f5_nfe_step", "label": _("[F5] Шаги диффузии", "[F5] Diffusion Steps"), "type": "entry", "options": {"default": "32"},
                "help": _("Больше шагов — лучше качество, медленнее.", "More steps — better quality, slower.")},
                {"key": "f5rvc_f5_seed", "label": _("[F5] Seed", "[F5] Seed"), "type": "entry", "options": {"default": "0"},
                "help": _("Сид генерации F5‑TTS.", "Seed value for F5‑TTS.")},
                {"key": "f5rvc_f5_remove_silence", "label": _("[F5] Удалять тишину", "[F5] Remove Silence"), "type": "checkbutton", "options": {"default": True},
                "help": _("Обрезать тишину в начале/конце.", "Trim silence at head/tail.")},

                {"key": "f5rvc_rvc_pitch", "label": _("[RVC] Высота голоса (пт)", "[RVC] Pitch (semitones)"), "type": "entry", "options": {"default": "0"},
                "help": _("Смещение высоты в полутонах.", "Pitch shift in semitones.")},
                {"key": "f5rvc_index_rate", "label": _("[RVC] Соотн. индекса", "[RVC] Index Rate"), "type": "entry", "options": {"default": "0.75"},
                "help": _("Степень влияния .index (0..1).", "How much .index affects result (0..1).")},
                {"key": "f5rvc_protect", "label": _("[RVC] Защита согласных", "[RVC] Consonant Protection"), "type": "entry", "options": {"default": "0.33"},
                "help": _("Защита глухих согласных (0..0.5).", "Protect voiceless consonants (0..0.5).")},
                {"key": "f5rvc_filter_radius", "label": _("[RVC] Радиус фильтра F0", "[RVC] F0 Filter Radius"), "type": "entry", "options": {"default": "3"},
                "help": _("Сглаживание кривой F0 (рекоменд. ≥3).", "Smooth F0 curve (recommended ≥3).")},
                {"key": "f5rvc_rvc_rms_mix_rate", "label": _("[RVC] Смешивание RMS", "[RVC] RMS Mixing"), "type": "entry", "options": {"default": "0.5"},
                "help": _("Смешивание громкости исходника и RVC (0..1).", "Mix source loudness and RVC result (0..1).")},
                {"key": "f5rvc_is_half", "label": _("[RVC] Half-precision", "[RVC] Half-precision"), "type": "combobox",
                "options": {"values": ["True", "False"], "default": "True"},
                "help": _("FP16 для RVC на совместимых GPU.", "FP16 for RVC on compatible GPUs.")},
                {"key": "f5rvc_f0method", "label": _("[RVC] Метод F0", "[RVC] F0 Method"), "type": "combobox",
                "options": {"values": ["pm", "rmvpe", "crepe", "harvest", "fcpe", "dio"], "default": "rmvpe"},
                "help": _("Алгоритм извлечения высоты тона.", "Pitch extraction algorithm.")},
                {"key": "f5rvc_use_index_file", "label": _("[RVC] Исп. .index файл", "[RVC] Use .index file"), "type": "checkbutton", "options": {"default": True},
                "help": _("Улучшает совпадение тембра.", "Improves timbre matching.")},

                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"},
                "help": _("Итоговая громкость.", "Final loudness.")},
                {"key": "f5rvc_use_ruaccent", "label": _("Использовать RUAccent", "Use RUAccent"), "type": "checkbutton", "options": {"default": False},
                "help": _("Улучшение ударений для русского.", "Better Russian stress handling.")}
            ]
        }
    ]
    def get_model_configs(self) -> List[Dict[str, Any]]:
        return self.MODEL_CONFIGS

    def _load_module(self):
        if self.f5_pipeline_module is not None:
            return
        if getattr(self, "_import_attempted", False):
            return

        self._import_attempted = True
        try:
            from handlers.voice_models.pipelines.f5_pipeline import F5TTSPipeline
            self.f5_pipeline_module = F5TTSPipeline
        except ImportError as ex:
            # Без exc_info, чтобы не заливать лог трейсами
            logger.info(f"F5_TTS: {ex}")
            self.f5_pipeline_module = None

    def get_display_name(self) -> str:
        mode = self._mode()
        if mode == "high":
            return "F5-TTS"
        elif mode == "high+low":
            return "F5-TTS + RVC"
        return None

    def is_installed(self, model_id) -> bool:
        self._load_module()
        model_dir = os.path.join("checkpoints", "F5-TTS")
        ckpt_path = os.path.join(model_dir, "model.safetensors")
        vocab_path = os.path.join(model_dir, "vocab.txt")
        
        if self.f5_pipeline_module is None:
            return False
        
        if not (os.path.exists(ckpt_path) and os.path.exists(vocab_path)):
            return False
        
        mode = model_id
        if mode == "high+low":
            if self.rvc_handler is None or not self.rvc_handler.is_installed("low"):
                return False
        
        return True

    def install(self, model_id) -> bool:
        mode = model_id
        
        # Устанавливаем сам F5-TTS, если его еще нет
        self._load_module()
        if self.f5_pipeline_module is None:
            if not self._install_f5_dependencies():
                return False
        
        mode = model_id

        # Для комбинированной модели доустанавливаем RVC
        if mode == "high+low":
            if self.rvc_handler and not self.rvc_handler.is_installed("low"):
                logger.info("Компонент F5-TTS установлен, приступаем к установке RVC...")
                return self.rvc_handler.install("low")
        
        return True
    
    
    def _install_f5_dependencies(self):
        """
        Установка F5-TTS.

        • Если метод вызван в GUI-потоке без внешних колбэков – создаёт своё окно.
        • Если вызван из воркера и у LocalVoice присутствуют
        _external_progress / _external_status / _external_log –
        окно НЕ создаётся, все сообщения уводятся во внешние колбэки.
        """
        logger.info("[DEBUG] download_f5_tts_internal вошёл")
        try:
            progress_cb = getattr(self.parent, "_external_progress", lambda *_: None)
            status_cb   = getattr(self.parent, "_external_status",   lambda *_: None)
            log_cb      = getattr(self.parent, "_external_log",      lambda *_: None)

            installer = PipInstaller(
                script_path=r"libs\python\python.exe",
                libs_path="Lib",
                update_status=status_cb,
                update_log=log_cb,
                progress_window=None,
                update_progress=progress_cb
            )
            logger.info("[DEBUG] PipInstaller создан, запускаем pip install")

            progress_cb(5)
            log_cb(_("Начало установки F5-TTS...", "Starting F5-TTS installation..."))

            # PyTorch (если надо)
            if self.parent.provider == "NVIDIA" and not self.parent.is_cuda_available():
                status_cb(_("Установка PyTorch (cu128)...", "Installing PyTorch (cu128)..."))
                progress_cb(10)
                if not installer.install_package(
                    ["torch==2.7.1", "torchaudio==2.7.1"],
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu128"],
                    description="Install PyTorch cu128"
                ):
                    status_cb(_("Ошибка PyTorch", "PyTorch error"))
                    return False

            progress_cb(25)

            # ВКЛЮЧИЛ cached_path, чтобы потом не падать при импорте f5_pipeline
            if not installer.install_package(
                ["f5-tts", "google-api-core", "numpy==1.26.0", "librosa==0.9.1", "numba==0.60.0", "cached_path"],
                description=_("Установка f5-tts...", "Installing f5-tts...")
            ):
                return False
            
            # На всякий случай librosa отдельно (оставлено из вашего кода)
            if not installer.install_package(
                "librosa==0.9.1",
                description=_("Установка дополнительной библиотеки librosa...", "Installing additional library librosa...")
            ):
                return False

            progress_cb(35)
            
            # Установка RUAccent (необяз.)
            status_cb(_("Установка RUAccent...", "Installing RUAccent..."))
            if not installer.install_package(
                "ruaccent",
                description=_("Установка ruaccent...", "Installing ruaccent...")
            ):
                log_cb(_("Предупреждение: не удалось установить RUAccent", "Warning: Failed to install RUAccent"))

            progress_cb(50)

            # Скачивание весов — без изменений...
            import requests, math, os, time

            model_dir = os.path.join("checkpoints", "F5-TTS")
            os.makedirs(model_dir, exist_ok=True)

            def _fmt_bytes(n):
                try:
                    n = float(n)
                except Exception:
                    return "?"
                for unit in ["B", "KB", "MB", "GB"]:
                    if n < 1024.0:
                        return f"{n:.1f} {unit}"
                    n /= 1024.0
                return f"{n:.1f} TB"

            def _fmt_eta(seconds: float) -> str:
                seconds = max(0, int(seconds))
                if seconds < 3600:
                    m, s = divmod(seconds, 60)
                    return f"{m:02d}:{s:02d}"
                h, rem = divmod(seconds, 3600)
                m, s = divmod(rem, 60)
                return f"{h}:{m:02d}:{s:02d}"

            def dl(url, dest, descr, start_prog, end_prog):
                if os.path.exists(dest):
                    progress_cb(end_prog)
                    status_cb(_(f"{descr} — уже скачано.", f"{descr} — already downloaded."))
                    return

                status_cb(descr)
                r = requests.get(url, stream=True, timeout=(10, 30))
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                done = 0
                start_t = time.time()
                last_status_t = start_t

                chunk = 1024 * 1024
                with open(dest, "wb") as fh:
                    for part in r.iter_content(chunk_size=chunk):
                        if not part:
                            continue
                        fh.write(part)
                        done += len(part)

                        now = time.time()
                        if total:
                            pct = done / total
                            prog = start_prog + (end_prog - start_prog) * pct
                            progress_cb(min(99, int(prog)))

                            elapsed = max(0.001, now - start_t)
                            speed = done / elapsed  # bytes/sec
                            eta = (total - done) / speed if speed > 0 else None

                            if now - last_status_t >= 0.5:
                                status_cb(
                                    _(
                                        f"{descr} ({_fmt_bytes(done)}/{_fmt_bytes(total)}, {_fmt_bytes(speed)}/s"
                                        + (f", ETA {_fmt_eta(eta)})" if eta else ")"),
                                        f"{descr} ({_fmt_bytes(done)}/{_fmt_bytes(total)}, {_fmt_bytes(speed)}/s"
                                        + (f", ETA {_fmt_eta(eta)})" if eta else ")")
                                    )
                                )
                                last_status_t = now
                        else:
                            if now - last_status_t >= 0.5:
                                elapsed = max(0.001, now - start_t)
                                speed = done / elapsed
                                status_cb(
                                    _(
                                        f"{descr} ({_fmt_bytes(done)} загружено, {_fmt_bytes(speed)}/s)",
                                        f"{descr} ({_fmt_bytes(done)} downloaded, {_fmt_bytes(speed)}/s)"
                                    )
                                )
                                last_status_t = now

                progress_cb(end_prog)
                status_cb(_(f"{descr} — готово.", f"{descr} — done."))

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

            progress_cb(100)
            status_cb(_("Установка F5-TTS завершена.", "F5-TTS installation complete."))

            # ВАЖНО: сбрасываем флаг и ещё раз пробуем импортнуть pipeline
            setattr(self, "_import_attempted", False)
            self._load_module()

            return True

        except Exception as e:
            logger.error(f"Ошибка установки F5-TTS: {e}", exc_info=True)
            if hasattr(self.parent, '_external_log'):
                self.parent._external_log(f"ERROR: {e}")
            return False

    def uninstall(self, model_id) -> bool:
        mode = model_id
        if mode == "high":
            return self.parent._uninstall_component("F5-TTS", "f5-tts")
        elif mode == "high+low":
            # Для комбинированной модели удаляем только F5-TTS компонент
            return self.parent._uninstall_component("F5-TTS", "f5-tts")
        else:
            logger.error("Неизвестная модель для удаления.")
            return False

    def cleanup_state(self):
        super().cleanup_state()
        self.current_f5_pipeline = None
        self.f5_pipeline_module = None
        self.ruaccent_instance = None
        
        if self.rvc_handler and self.rvc_handler.initialized:
            self.rvc_handler.cleanup_state()
        
        logger.info(f"Состояние для модели {self.model_id} сброшено.")

    def initialize(self, init: bool = False) -> bool:
        if self.initialized:
            return True

        self._load_module()
        if self.f5_pipeline_module is None:
            logger.error("Модуль f5_pipeline не установлен или не загружен.")
            return False
        
        mode = self._mode()
        
        if self.current_f5_pipeline is None:
            model_dir = os.path.join("checkpoints", "F5-TTS")
            ckpt_path = os.path.join(model_dir, "model.safetensors")
            vocab_path = os.path.join(model_dir, "vocab.txt")

            if not all(os.path.exists(p) for p in [ckpt_path, vocab_path]):
                logger.error(f"Не найдены файлы модели F5-TTS в {model_dir}. Переустановите модель.")
                return False
            
            settings = self.parent.load_model_settings(mode)
            device_key = "f5rvc_f5_device" if mode == "high+low" else "device"
            device = settings.get(device_key, "cuda" if self.parent.provider == "NVIDIA" else "cpu")
            
            self.current_f5_pipeline = self.f5_pipeline_module(
                model="F5TTS_v1_Base", 
                ckpt_file=ckpt_path, 
                vocab_file=vocab_path, 
                device=device
            )
            logger.info(f"F5-TTS Pipeline инициализирован на устройстве: {device}.")

        if mode == "high+low":
            if self.rvc_handler and not self.rvc_handler.initialized:
                logger.info("Инициализация RVC компонента для 'high+low'...")
                rvc_success = self.rvc_handler.initialize(init=False)
                if not rvc_success:
                    logger.error("Не удалось инициализировать RVC компонент для 'high+low'.")
                    return False

        self.initialized = True

        if init:
            init_text = f"Инициализация модели {self.model_id}" if self.parent.voice_language == "ru" else f"{self.model_id} Model Initialization"
            logger.info(f"Выполнение тестового прогона для {self.model_id}...")
            try:
                main_loop = self.events.emit_and_wait(Events.Core.GET_EVENT_LOOP, timeout=1.0)[0]
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

    def _load_ruaccent_if_needed(self, settings: dict):
        """Загружает RUAccent если включен в настройках и еще не загружен"""
        mode = self._mode()
        use_ruaccent_key = "f5rvc_use_ruaccent" if mode == "high+low" else "use_ruaccent"
        
        if settings.get(use_ruaccent_key, False) and self.ruaccent_instance is None:
            try:
                from ruaccent import RUAccent
                self.ruaccent_instance = RUAccent()
                
                device = "CUDA" if self.parent.provider == "NVIDIA" else "CPU"
                workdir = os.path.join("checkpoints", "ruaccent_models")
                os.makedirs(workdir, exist_ok=True)
                
                self.ruaccent_instance.load(
                    omograph_model_size='turbo3.1',
                    use_dictionary=True,
                    device=device,
                    workdir=workdir,
                    tiny_mode=False
                )
                logger.info(f"RUAccent загружен на устройстве: {device}")
            except Exception as e:
                logger.warning(f"Не удалось загрузить RUAccent: {e}")
                self.ruaccent_instance = None

    def _apply_ruaccent(self, text: str) -> str:
        """Применяет RUAccent к тексту если он загружен"""
        if self.ruaccent_instance is None:
            return text
        
        try:
            return self.ruaccent_instance.process_all(text)
        except Exception as e:
            logger.warning(f"Ошибка при применении RUAccent: {e}")
            return text

    async def voiceover(self, text: str, character: Optional[Any] = None, **kwargs) -> Optional[str]:
        if not self.initialized:
            raise Exception(f"Модель {self.model_id} не инициализирована.")
        
        try:
            mode = self._mode()
            settings = self.parent.load_model_settings(mode)
            is_combined_model = mode == "high+low"
            
            # Загружаем RUAccent если нужно
            self._load_ruaccent_if_needed(settings)
            
            # Определяем ключи параметров в зависимости от режима
            speed_key = "f5rvc_f5_speed" if is_combined_model else "speed"
            remove_silence_key = "f5rvc_f5_remove_silence" if is_combined_model else "remove_silence"
            nfe_step_key = "f5rvc_f5_nfe_step" if is_combined_model else "nfe_step"
            seed_key = "f5rvc_f5_seed" if is_combined_model else "seed"

            reference_postfix = kwargs.get("reference_postfix", "default")

            # Используем get_character_voice_paths для получения путей
            voice_paths = get_character_voice_paths(character, self.parent.provider)
            
            ref_audio_path = None
            ref_text_content = ""
            
            # Пробуем найти файлы персонажа с постфиксом
            if character and hasattr(character, 'short_name'):
                char_name = character.short_name
                potential_audio_path = os.path.join("Models", f"{char_name}_Cuts", f"{char_name}_{reference_postfix}.wav")
                potential_text_path = os.path.join("Models", f"{char_name}_Cuts", f"{char_name}_{reference_postfix}.txt")
                if os.path.exists(potential_audio_path):
                    ref_audio_path = potential_audio_path
                    if os.path.exists(potential_text_path):
                        with open(potential_text_path, "r", encoding="utf-8") as f: 
                            ref_text_content = f.read().strip()
            
            # Если не нашли с постфиксом, используем стандартные пути из voice_paths для F5
            if not ref_audio_path and os.path.exists(voice_paths['f5_voice_filename']):
                ref_audio_path = voice_paths['f5_voice_filename']
                if os.path.exists(voice_paths['f5_voice_text']):
                    with open(voice_paths['f5_voice_text'], "r", encoding="utf-8") as f: 
                        ref_text_content = f.read().strip()
            
            # Fallback на обычные файлы персонажа
            if not ref_audio_path and os.path.exists(voice_paths['clone_voice_filename']):
                ref_audio_path = voice_paths['clone_voice_filename']
                if os.path.exists(voice_paths['clone_voice_text']):
                    with open(voice_paths['clone_voice_text'], "r", encoding="utf-8") as f: 
                        ref_text_content = f.read().strip()
            
            # Fallback на Mila если персонаж не найден
            if not ref_audio_path:
                default_voice_paths = get_character_voice_paths(None, self.parent.provider)
                if os.path.exists(default_voice_paths['f5_voice_filename']):
                    ref_audio_path = default_voice_paths['f5_voice_filename']
                    if os.path.exists(default_voice_paths['f5_voice_text']):
                        with open(default_voice_paths['f5_voice_text'], "r", encoding="utf-8") as f: 
                            ref_text_content = f.read().strip()
                elif os.path.exists(default_voice_paths['clone_voice_filename']):
                    ref_audio_path = default_voice_paths['clone_voice_filename']
                    if os.path.exists(default_voice_paths['clone_voice_text']):
                        with open(default_voice_paths['clone_voice_text'], "r", encoding="utf-8") as f: 
                            ref_text_content = f.read().strip()
            
            if not ref_audio_path:
                raise FileNotFoundError("Для F5-TTS требуется референсное аудио, но оно не найдено.")
            
            # Применяем RUAccent к текстам если включено
            if self.ruaccent_instance is not None:
                text = self._apply_ruaccent(text)
                if ref_text_content:
                    ref_text_content = self._apply_ruaccent(ref_text_content)
            
            hash_object = hashlib.sha1(f"{text[:20]}_{datetime.now().timestamp()}".encode())
            output_path = os.path.join("temp", f"f5_raw_{hash_object.hexdigest()[:10]}.wav")
            os.makedirs("temp", exist_ok=True)

            seed_processed = int(settings.get(seed_key, 0))
            vol = str(settings.get("volume", "1.0"))
            if seed_processed <= 0 or seed_processed > 2**31 - 1: seed_processed = 42
            
            await asyncio.to_thread(
                self.current_f5_pipeline.generate,
                text_to_generate=text,
                output_path=output_path,
                ref_audio=ref_audio_path,
                ref_text=ref_text_content,
                speed=float(settings.get(speed_key, 1.0)),
                remove_silence=settings.get(remove_silence_key, True),
                nfe_step=int(settings.get(nfe_step_key, 32)),
                seed=seed_processed
            )

            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                return None
            
            stereo_output_path = output_path.replace("_raw", "_stereo")
            converted_file = self.parent.convert_wav_to_stereo(output_path, stereo_output_path, volume=vol)

            processed_output_path = stereo_output_path if converted_file and os.path.exists(converted_file) else output_path
            if processed_output_path == stereo_output_path:
                try: os.remove(output_path)
                except OSError: pass
            
            final_output_path = processed_output_path

            if mode == "high+low":
                if self.rvc_handler:
                    logger.info(f"Применяем RVC с параметрами F5+RVC к файлу: {final_output_path}")
                    
                    # Получаем f5_rvc параметры из настроек
                    rvc_output_path = await self.rvc_handler.apply_rvc_to_file(
                        filepath=final_output_path,
                        character=character,  # Передаем персонажа
                        pitch=float(settings.get("f5rvc_rvc_pitch", 0)),
                        index_rate=float(settings.get("f5rvc_index_rate", 0.75)),
                        protect=float(settings.get("f5rvc_protect", 0.33)),
                        filter_radius=int(settings.get("f5rvc_filter_radius", 3)),
                        rms_mix_rate=float(settings.get("f5rvc_rvc_rms_mix_rate", 0.5)),
                        is_half=settings.get("f5rvc_is_half", "True").lower() == "true",
                        f0method=settings.get("f5rvc_f0method", None),
                        use_index_file=settings.get("f5rvc_use_index_file", True),
                        volume=vol
                    )
                    
                    if rvc_output_path and os.path.exists(rvc_output_path):
                        if final_output_path != rvc_output_path:
                            try: os.remove(final_output_path)
                            except OSError: pass
                        final_output_path = rvc_output_path
                    else:
                        logger.warning("Ошибка во время обработки RVC. Возвращается результат до RVC.")
                else:
                    logger.warning("Модель 'high+low' требует RVC, но обработчик не был предоставлен.")
            
            connected_to_game = self.events.emit_and_wait(Events.Server.GET_GAME_CONNECTION)[0]
            if connected_to_game:
                self.events.emit(Events.Server.SET_PATCH_TO_SOUND_FILE, final_output_path)

            return final_output_path
        except Exception as e:
            logger.error(f"Ошибка при создании озвучки с F5-TTS ({self.model_id}): {e}")
            traceback.print_exc()
            return None
    
    def _mode(self) -> str:
        """
        Возвращает текущий «режим» (high / high+low),
        выбранный в LocalVoice.initialize_model().
        """
        return self.parent.current_model_id or "high"