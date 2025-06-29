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


    def get_display_name(self) -> str:
        mode = self._mode()
        if mode in "medium":
            return "Fish Speech"
        elif mode in "medium+":
            return "Fish Speech+"
        if mode in "medium+low":
            return "Fish Speech+ + RVC"
        return None
    
    def is_installed(self) -> bool:
        self._load_module()
        mode = self._mode()

        
        if self.fish_speech_module is None:
            return False
        
        if mode in ("medium+", "medium+low"):
            if not self.parent.is_triton_installed():
                return False
        
        if mode == "medium+low":
            if self.rvc_handler is None or not self.rvc_handler.is_installed():
                return False
        
        return True

    def install(self) -> bool:
        if self.fish_speech_module is None:
            if not self.parent.download_fish_speech_internal():
                return False

        mode = self._mode()
        if mode in ("medium+", "medium+low") and not self.parent.is_triton_installed():
            if mode == "medium+low" and not self.rvc_handler.is_installed():
                return self.rvc_handler.install() and self.parent.download_triton_internal()
            return self.parent.download_triton_internal()
        
        
        return True

    def uninstall(self) -> bool:
        
        mode = self._mode()
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
            settings = self.load_model_settings()
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
            settings = self.load_model_settings()
            is_combined_model = mode == "medium+low"
            
            temp_key = "fsprvc_fsp_temperature" if is_combined_model else "temperature"
            top_p_key = "fsprvc_fsp_top_p" if is_combined_model else "top_p"
            rep_penalty_key = "fsprvc_fsp_repetition_penalty" if is_combined_model else "repetition_penalty"
            chunk_len_key = "fsprvc_fsp_chunk_length" if is_combined_model else "chunk_length"
            max_tokens_key = "fsprvc_fsp_max_tokens" if is_combined_model else "max_new_tokens"

            reference_audio_path = self.parent.clone_voice_filename if self.parent.clone_voice_filename and os.path.exists(self.parent.clone_voice_filename) else None
            reference_text = ""
            if reference_audio_path and self.parent.clone_voice_text and os.path.exists(self.parent.clone_voice_text):
                with open(self.parent.clone_voice_text, "r", encoding="utf-8") as file:
                    reference_text = file.read().strip()

            sample_rate, audio_data = self.current_fish_speech(
                text=text,
                reference_audio=reference_audio_path,
                reference_audio_text=reference_text,
                top_p=float(settings.get(top_p_key, 0.7)),
                temperature=float(settings.get(temp_key, 0.7)),
                repetition_penalty=float(settings.get(rep_penalty_key, 1.2)),
                max_new_tokens=int(settings.get(max_tokens_key, 1024)),
                chunk_length=int(settings.get(chunk_len_key, 200)),
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
                    logger.info(f"Применяем RVC (через инъекцию) к файлу: {final_output_path}")
                    # Используем метод родителя, который уже умеет обрабатывать RVC
                    rvc_output_path = await self.rvc_handler.apply_rvc_to_file(final_output_path, original_model_id=self.model_id)
                    
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