import os
import sys
import importlib
import traceback
import hashlib
from datetime import datetime
import asyncio

from .base_model import IVoiceModel
from typing import Optional, Any
from main_logger import logger

from settings_manager import SettingsManager
from utils import getTranslationVariant as _

import requests
import math
from PyQt6.QtCore import QTimer
from utils.pip_installer import PipInstaller

class F5TTSModel(IVoiceModel):
    def __init__(self, parent: 'LocalVoice', model_id: str, rvc_handler: Optional[IVoiceModel] = None):
        super().__init__(parent, model_id)
        self.f5_pipeline_module = None
        self.current_f5_pipeline = None
        self.rvc_handler = rvc_handler

    def _load_module(self):
        try:
            from LocalPipelines.F5_TTS.f5_pipeline import F5TTSPipeline
            self.f5_pipeline_module = F5TTSPipeline
        except ImportError:
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
            gui = self.parent._create_installation_window(
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
            if self.parent.provider == "NVIDIA" and not self.parent.is_cuda_available():
                update_status(_("Установка PyTorch (cu124)...", "Installing PyTorch (cu124)..."))
                update_progress(10)
                if not installer.install_package(
                    ["torch==2.7.1", "torchaudio==2.7.1"],
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu118"],
                    description="Install PyTorch cu128"
                ):
                    update_status(_("Ошибка PyTorch", "PyTorch error"))
                    return False

            update_progress(25)

            if not installer.install_package(
                ["f5-tts", "google-api-core"],
                description=_("Установка f5-tts...", "Installing f5-tts...")
            ):
                return False
            
            if not installer.install_package(
                    "librosa==0.9.1",
                    description=_("Установка дополнительной библиотеки librosa...", "Installing additional library librosa...")
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
            self._load_module()
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
        
        try:
            mode = self._mode()
            settings = self.parent.load_model_settings(mode)
            is_combined_model = mode == "high+low"
            
            # Определяем ключи параметров в зависимости от режима
            speed_key = "f5rvc_f5_speed" if is_combined_model else "speed"
            remove_silence_key = "f5rvc_f5_remove_silence" if is_combined_model else "remove_silence"
            nfe_step_key = "f5rvc_f5_nfe_step" if is_combined_model else "nfe_step"
            seed_key = "f5rvc_f5_seed" if is_combined_model else "seed"
            
            
            # logger.info("-"*100)
            # logger.info(int(settings.get(nfe_step_key, 32)))
            # logger.info(nfe_step_key)
            # logger.info(is_combined_model)
            # logger.info("-"*100)

            reference_postfix = kwargs.get("reference_postfix", "default")

            ref_audio_path = None
            ref_text_content = ""
            if character and hasattr(character, 'short_name'):
                char_name = character.short_name
                potential_audio_path = os.path.join("Models", f"{char_name}_Cuts", f"{char_name}_{reference_postfix}.wav")
                potential_text_path = os.path.join("Models", f"{char_name}_Cuts", f"{char_name}_{reference_postfix}.txt")
                if os.path.exists(potential_audio_path):
                    ref_audio_path = potential_audio_path
                    if os.path.exists(potential_text_path):
                        with open(potential_text_path, "r", encoding="utf-8") as f: 
                            ref_text_content = f.read().strip()
            
            if not ref_audio_path:
                default_audio_path = os.path.join("Models", "Mila.wav")
                default_text_path = os.path.join("Models", "Mila.txt")
                if os.path.exists(default_audio_path):
                    ref_audio_path = default_audio_path
                    if os.path.exists(default_text_path):
                        with open(default_text_path, "r", encoding="utf-8") as f: 
                            ref_text_content = f.read().strip()
            
            if not ref_audio_path:
                raise FileNotFoundError("Для F5-TTS требуется референсное аудио, но оно не найдено.")
            
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
                        pitch=float(settings.get("f5rvc_rvc_pitch", 0)),
                        index_rate=float(settings.get("f5rvc_index_rate", 0.75)),
                        protect=float(settings.get("f5rvc_protect", 0.33)),
                        filter_radius=int(settings.get("f5rvc_filter_radius", 3)),
                        rms_mix_rate=float(settings.get("f5rvc_rvc_rms_mix_rate", 0.5)),
                        is_half=settings.get("f5rvc_is_half", "True").lower() == "true",
                        f0method=settings.get("f5rvc_f0method", None),
                        use_index_file=settings.get("f5rvc_use_index_file", True)
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
            
            if self.parent.parent and hasattr(self.parent.parent, 'ConnectedToGame') and self.parent.parent.ConnectedToGame:
                self.parent.parent.patch_to_sound_file = final_output_path

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