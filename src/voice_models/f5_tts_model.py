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

    def is_installed(self) -> bool:
        self._load_module()
        model_dir = os.path.join("checkpoints", "F5-TTS")
        ckpt_path = os.path.join(model_dir, "model.safetensors")
        vocab_path = os.path.join(model_dir, "vocab.txt")
        
        if self.f5_pipeline_module is None:
            return False
        
        if not (os.path.exists(ckpt_path) and os.path.exists(vocab_path)):
            return False
        
        mode = self._mode()
        if mode == "high+low":
            if self.rvc_handler is None or not self.rvc_handler.is_installed():
                return False
        
        return True

    def install(self) -> bool:
        mode = self._mode()
        
        if self.f5_pipeline_module is None:
            if not self.parent.download_f5_tts_internal():
                return False
        
        if mode == "high+low" and self.rvc_handler and not self.rvc_handler.is_installed():
            return self.rvc_handler.install()
        
        return True

    def uninstall(self) -> bool:
        mode = self._mode()
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
            converted_file = self.parent.convert_wav_to_stereo(output_path, stereo_output_path)

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