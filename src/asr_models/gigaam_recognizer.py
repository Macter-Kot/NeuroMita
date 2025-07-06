import os
import time
import wave
import asyncio
from typing import Optional, List
from collections import deque
import numpy as np
import onnxruntime as rt
from asr_models.speech_recognizer_base import SpeechRecognizerInterface
from utils import getTranslationVariant as _
from utils.gpu_utils import check_gpu_provider

def load_my_onnx_sessions(
    onnx_dir: str,
    model_version: str,
    providers,
) -> List[rt.InferenceSession]:
    if isinstance(providers, str):
        providers = [providers]
    else:
        providers = list(providers)
    if "CPUExecutionProvider" not in providers:
        providers.append("CPUExecutionProvider")

    if "_" in model_version:
        version, model_type = model_version.split("_", 1)
    else:
        version, model_type = "v2", model_version

    opts = rt.SessionOptions()
    opts.intra_op_num_threads = 16
    opts.execution_mode = rt.ExecutionMode.ORT_SEQUENTIAL

    sessions: List[rt.InferenceSession] = []

    if model_type == "ctc":
        model_path = os.path.join(onnx_dir, f"{version}_{model_type}.onnx")
        sessions.append(rt.InferenceSession(model_path,
                                            providers=providers,
                                            sess_options=opts))
    else:
        base = os.path.join(onnx_dir, f"{version}_{model_type}")
        for part in ("encoder", "decoder", "joint"):
            path = f"{base}_{part}.onnx"
            sessions.append(rt.InferenceSession(path,
                                                providers=providers,
                                                sess_options=opts))
    return sessions

class GigaAMRecognizer(SpeechRecognizerInterface):
    def __init__(self, pip_installer, logger):
        super().__init__(pip_installer, logger)
        self._torch = None
        self._gigaam = None
        self._onnx_runtime = None
        self._gigaam_model_instance = None
        self._gigaam_onnx_sessions = None
        self._current_gpu = None
        self.gigaam_model = "v2_rnnt"
        self.gigaam_device = "auto"
        self.gigaam_onnx_export_path = "SpeechRecognitionModels/GigaAM_ONNX"
        self.FAILED_AUDIO_DIR = "FailedAudios"
        
    def _show_install_warning(self, packages: list):
        package_str = ", ".join(packages)
        self.logger.warning("="*80)
        self.logger.warning(_(
            f"ВНИМАНИЕ: Для работы выбранного модуля распознавания речи требуются библиотеки: {package_str}.",
            f"WARNING: The selected speech recognition module requires libraries: {package_str}."
        ))
        self.logger.warning(_(
            "Сейчас начнется их автоматическая установка. Это может занять некоторое время.",
            "Automatic installation will now begin. This may take some time."
        ))
        self.logger.warning(_(
            "Также, после установки, будет загружена модель распознавания, которая может занимать до 1 ГБ дискового пространства.",
            "Also, after installation, a recognition model will be downloaded, which can take up to 1 GB of disk space."
        ))
        self.logger.warning("="*80)
        time.sleep(3)
        
    def set_options(self, device: str, model: str = None, onnx_path: str = None):
        self.gigaam_device = device
        if model:
            self.gigaam_model = model
        if onnx_path:
            self.gigaam_onnx_export_path = onnx_path
        self.logger.info(f"Устройство для GigaAM установлено на: {device}")
    
    async def install(self) -> bool:
        try:
            if self._torch is None:
                try:
                    import torch
                except ImportError:
                    if self._current_gpu is None:
                        self._current_gpu = check_gpu_provider() or "CPU"
                    
                    if self._current_gpu == "NVIDIA":
                        success = self.pip_installer.install_package(
                            ["torch==2.7.1", "torchaudio==2.7.1"],
                            description=_("Установка PyTorch с поддержкой CUDA...", "Installing PyTorch with CUDA support..."),
                            extra_args=["--index-url", "https://download.pytorch.org/whl/cu128"]
                        )
                    else:
                        success = self.pip_installer.install_package(
                            ["torch==2.7.1", "torchaudio==2.7.1"],
                            description=_("Установка PyTorch CPU...", "Installing PyTorch CPU..."),
                        )
                    if not success:
                        raise ImportError("Не удалось установить torch, необходимый для GigaAM.")
                    import torch
                try:
                    import omegaconf
                except ImportError:
                    success = self.pip_installer.install_package(
                        "omegaconf",
                        description=_("Установка omegaconf...", "Installing omegaconf...")
                    )
                    if not success:
                        raise ImportError("Не удалось установить omegaconf, необходимый для GigaAM.")
                
                import omegaconf, typing, collections
                torch.serialization.add_safe_globals([omegaconf.dictconfig.DictConfig, omegaconf.base.ContainerMetadata, typing.Any, dict, collections.defaultdict, omegaconf.nodes.AnyNode, omegaconf.nodes.Metadata, omegaconf.listconfig.ListConfig, list, int])
                self.logger.warning("TORCH ADDED SAFE GLOBALS!")
                self._torch = torch

            if self._gigaam is None:
                try:
                    import gigaam
                except ImportError:
                    self._show_install_warning(["gigaam"])
                    success = self.pip_installer.install_package(
                        ["gigaam", "hydra-core", "sentencepiece"],
                        description=_("Установка GigaAM...", "Installing GigaAM..."),
                        extra_args=["--no-deps"]
                    )
                    if not success:
                        raise ImportError("Не удалось установить GigaAM.")
                    import gigaam
                self._gigaam = gigaam
            return True
        except ImportError as e:
            self.logger.critical(f"Критическая ошибка: не удалось импортировать или установить библиотеку для GigaAM: {e}")
            return False
    
    async def init(self, **kwargs) -> bool:
        if self._gigaam_model_instance is not None or self._gigaam_onnx_sessions is not None:
            return True

        if self._gigaam is None:
            self.logger.error("Модуль GigaAM не был импортирован. Инициализация невозможна.")
            return False
        
        if self._current_gpu is None:
            self._current_gpu = check_gpu_provider() or "CPU"

        device_choice = self.gigaam_device
        is_nvidia = self._current_gpu == "NVIDIA"

        if is_nvidia and device_choice in ["auto", "cuda", "cpu"]:
            device = "cuda" if device_choice in ["auto", "cuda"] else "cpu"
            self.logger.info(f"Инициализация GigaAM для NVIDIA на устройстве: {device}")
            self.logger.warning(_(
                f"Начинается загрузка модели GigaAM ({self.gigaam_model}). Размер ~1 ГБ. Пожалуйста, подождите...",
                f"Starting download of GigaAM model ({self.gigaam_model}). Size ~1 GB. Please wait..."
            ))
            try:
                model = self._gigaam.load_model(self.gigaam_model, device=device)
                self._gigaam_model_instance = model
                self.logger.info(f"Модель GigaAM '{self.gigaam_model}' успешно загружена на {device}.")
                self._is_initialized = True
                return True
            except Exception as e:
                self.logger.error(f"Ошибка загрузки PyTorch модели GigaAM: {e}", exc_info=True)
                return False
        else:
            provider = 'CPUExecutionProvider'
            if device_choice in ["auto", "dml"] and not is_nvidia:
                provider = 'DmlExecutionProvider'
            
            self.logger.info(f"Инициализация GigaAM через ONNX с провайдером: {provider}")

            if self._onnx_runtime is None:
                try:
                    import onnxruntime
                except ImportError:
                    deps_to_install = ["onnx", "onnxruntime"]
                    desc = _("Установка ONNX Runtime...", "Installing ONNX Runtime...")
                    if provider == 'DmlExecutionProvider':
                        deps_to_install.append("onnxruntime-directml")
                        desc = _("Установка ONNX Runtime с поддержкой DirectML...", "Installing ONNX Runtime with DirectML support...")
                    
                    self._show_install_warning(deps_to_install)
                    self.pip_installer.install_package(deps_to_install, description=desc)
                    import onnxruntime
                self._onnx_runtime = onnxruntime

            onnx_dir = self.gigaam_onnx_export_path
            os.makedirs(onnx_dir, exist_ok=True)
            
            encoder_path = os.path.join(onnx_dir, f"{self.gigaam_model}_encoder.onnx")

            if not os.path.exists(encoder_path):
                self.logger.warning(_(
                    f"Модель GigaAM ONNX не найдена. Начинается экспорт. Это единоразовый процесс, который потребует загрузки ~1 ГБ и может занять несколько минут.",
                    f"GigaAM ONNX model not found. Exporting will now begin. This is a one-time process that will download ~1GB and may take several minutes."
                ))
                try:
                    temp_model = self._gigaam.load_model(
                        self.gigaam_model,
                        device="cpu",
                        fp16_encoder=False,
                        use_flash=False
                    )
                    temp_model.to_onnx(dir_path=onnx_dir)
                    del temp_model
                    if self._torch.cuda.is_available():
                        self._torch.cuda.empty_cache()
                    self.logger.info(f"Модель GigaAM успешно экспортирована в ONNX в директорию: {onnx_dir}")
                except Exception as e:
                    self.logger.error(f"Не удалось экспортировать модель GigaAM в ONNX: {e}", exc_info=True)
                    return False

            try:
                self.logger.info(f"Загрузка ONNX сессий из {onnx_dir}...")
                sessions = load_my_onnx_sessions(
                    onnx_dir,
                    self.gigaam_model,
                    provider
                )
                self._gigaam_onnx_sessions = sessions
                self.logger.info(f"ONNX сессии для GigaAM успешно загружены с провайдером {provider}.")
                self._is_initialized = True
                return True
            except Exception as e:
                self.logger.error(f"Ошибка загрузки ONNX сессий GigaAM: {e}", exc_info=True)
                return False
    
    async def transcribe(self, audio_data: np.ndarray, sample_rate: int) -> Optional[str]:
        if not self._is_initialized:
            return None
            
        pytorch_model = self._gigaam_model_instance
        onnx_sessions = self._gigaam_onnx_sessions

        if pytorch_model is None and onnx_sessions is None:
            self.logger.error("Распознаватель GigaAM не инициализирован.")
            return None
        
        from gigaam.onnx_utils import transcribe_sample

        TEMP_AUDIO_DIR = "TempAudios"
        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
        temp_filepath = os.path.join(TEMP_AUDIO_DIR, f"temp_gigaam_{time.time_ns()}.wav")
        
        try:
            audio_data_int16 = (audio_data * 32767).astype(np.int16)
            with wave.open(temp_filepath, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data_int16.tobytes())

            transcription = ""
            if pytorch_model:
                transcription = pytorch_model.transcribe(temp_filepath)
            elif onnx_sessions:
                model_type = self.gigaam_model.split("_", 1)[-1]
                transcription = transcribe_sample(
                        temp_filepath,
                        model_type,
                        onnx_sessions
                )

            if transcription and transcription.strip() != '':
                return transcription
            else:
                self.logger.info("GigaAM не распознал текст.")
                return None

        except Exception as e:
            self.logger.error(f"Ошибка во время распознавания GigaAM: {e}", exc_info=True)
            return None

        finally:
            if os.path.exists(temp_filepath):
                try:
                    os.remove(temp_filepath)
                except OSError as e:
                    self.logger.error(f"Не удалось удалить временный файл {temp_filepath}: {e}")
    
    async def live_recognition(self, microphone_index: int, handle_voice_callback, 
                              vad_model, active_flag, **kwargs) -> None:
        try:
            import sounddevice as sd
            import torch
        except ImportError as e:
            self.logger.error(f"Не удалось импортировать необходимые библиотеки: {e}")
            return
        
        sample_rate = kwargs.get('sample_rate', 16000)
        chunk_size = kwargs.get('chunk_size', 512)
        vad_threshold = kwargs.get('vad_threshold', 0.5)
        silence_timeout = kwargs.get('silence_timeout', 1.0)
        pre_buffer_duration = kwargs.get('pre_buffer_duration', 0.3)
        
        silence_chunks_needed = int(silence_timeout * sample_rate / chunk_size)
        pre_buffer_size = int(pre_buffer_duration * sample_rate / chunk_size)
        
        try:
            devices = sd.query_devices()
            input_devices = [dev['name'] for dev in devices if dev['max_input_channels'] > 0]
            mic_name = input_devices[microphone_index] if microphone_index < len(input_devices) else "Unknown"
            self.logger.info(f"Используется микрофон: {mic_name}")
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о микрофоне: {e}")
            return

        self.logger.info("Ожидание речи (GigaAM + Silero VAD с пред-буферизацией)...")

        pre_speech_buffer = deque(maxlen=pre_buffer_size)
        speech_buffer = []
        is_speaking = False
        silence_counter = 0

        with sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype='float32',
            blocksize=chunk_size,
            device=microphone_index
        ) as stream:
            while active_flag():
                audio_chunk, overflowed = stream.read(chunk_size)
                if overflowed:
                    self.logger.warning("Переполнение буфера аудиопотока!")

                if not is_speaking:
                    pre_speech_buffer.append(audio_chunk)

                audio_tensor = torch.from_numpy(audio_chunk.flatten())
                speech_prob = vad_model(audio_tensor, sample_rate).item()

                if speech_prob > vad_threshold:
                    if not is_speaking:
                        self.logger.debug("🟢 Начало речи. Захват из пред-буфера.")
                        is_speaking = True
                        speech_buffer.clear()
                        speech_buffer.extend(list(pre_speech_buffer))
                    
                    speech_buffer.append(audio_chunk)
                    silence_counter = 0
                
                elif is_speaking:
                    speech_buffer.append(audio_chunk)
                    silence_counter += 1
                    if silence_counter > silence_chunks_needed:
                        self.logger.debug("🔴 Конец речи. Отправка на распознавание.")
                        audio_to_process = np.concatenate(speech_buffer)
                        
                        is_speaking = False
                        speech_buffer.clear()
                        silence_counter = 0
                        
                        text = await self.transcribe(audio_to_process, sample_rate)
                        if text:
                            self.logger.info(f"GigaAM распознал: {text}")
                            await handle_voice_callback(text)
                        else:
                            await self._save_failed_audio(audio_to_process, sample_rate)
                
                await asyncio.sleep(0.01)
    
    async def _save_failed_audio(self, audio_data: np.ndarray, sample_rate: int):
        self.logger.info("Сохранение аудиофрагмента в папку Failed...")
        try:
            os.makedirs(self.FAILED_AUDIO_DIR, exist_ok=True)
            timestamp = int(time.time())
            filename = os.path.join(self.FAILED_AUDIO_DIR, f"failed_{timestamp}.wav")
            
            audio_data_int16 = (audio_data * 32767).astype(np.int16)

            with wave.open(filename, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(audio_data_int16.tobytes())
            self.logger.info(f"Фрагмент сохранен в: {filename}")
        except Exception as e:
            self.logger.error(f"Не удалось сохранить аудиофрагмент: {e}")
    
    def cleanup(self) -> None:
        self._torch = None
        self._gigaam = None
        self._onnx_runtime = None
        self._gigaam_model_instance = None
        self._gigaam_onnx_sessions = None
        self._is_initialized = False