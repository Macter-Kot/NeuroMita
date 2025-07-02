import os
import sys
import importlib
import traceback
import tempfile
import soundfile as sf
import asyncio
import re
from xml.sax.saxutils import escape

from .base_model import IVoiceModel
from typing import Optional, Any
from Logger import logger

import re
from PyQt6.QtCore import QTimer
from utils.PipInstaller import PipInstaller

from SettingsManager import SettingsManager
def getTranslationVariant(ru_str, en_str=""): return en_str if en_str and SettingsManager.get("LANGUAGE") == "EN" else ru_str
_ = getTranslationVariant

class EdgeTTS_RVC_Model(IVoiceModel):
    def __init__(self, parent: 'LocalVoice', model_id: str):
        # model_id здесь больше не используется для определения режима,
        # но остается для совместимости с интерфейсом.
        super().__init__(parent, model_id)
        self.tts_rvc_module = None
        self.current_tts_rvc = None
        self.current_silero_model = None
        self.current_silero_sample_rate = 48000
        self._load_module()

    def _load_module(self):
        try:
            from tts_with_rvc import TTS_RVC
            self.tts_rvc_module = TTS_RVC
        except ImportError:
            self.tts_rvc_module = None
    
    def get_display_name(self) -> str:
        return "EdgeTTS+RVC / Silero+RVC"

    def is_installed(self, model_id) -> bool:
        self._load_module()
        return self.tts_rvc_module is not None

    def install(self, model_id) -> bool:
        gui_elements = None
        try:
            gui_elements = self.parent._create_installation_window(
                title=_("Скачивание Edge-TTS + RVC", "Downloading Edge-TTS + RVC"),
                initial_status=_("Подготовка...", "Preparing...")
            )
            if not gui_elements:
                return False

            progress_window = gui_elements["window"]
            update_progress = gui_elements["update_progress"]
            update_status = gui_elements["update_status"]
            update_log = gui_elements["update_log"]

            installer = PipInstaller(
                script_path=r"libs\python\python.exe",
                libs_path="Lib",
                update_status=update_status,
                update_log=update_log,
                progress_window=progress_window
            )

            update_progress(10)
            update_log(_("Начало установки Edge-TTS + RVC...", "Starting Edge-TTS + RVC installation..."))

            if self.parent.provider in ["NVIDIA"] and not self.parent.is_cuda_available():
                update_status(_("Установка PyTorch с поддержкой CUDA 12.8...", "Installing PyTorch with CUDA 12.8 support..."))
                update_progress(20)
                success = installer.install_package(
                    ["torch==2.7.1", "torchaudio==2.7.1"],
                    description=_("Установка PyTorch с поддержкой CUDA 12.8...", "Installing PyTorch with CUDA 12.8 support..."),
                    extra_args=["--index-url", "https://download.pytorch.org/whl/cu118"],
                )

                if not success:
                    update_status(_("Ошибка при установке PyTorch", "Error installing PyTorch"))
                    QTimer.singleShot(5000, progress_window.close)
                    return False
                update_progress(50)
            else:
                update_progress(50) 

            update_status(_("Установка зависимостей...", "Installing dependencies..."))
            success = installer.install_package(
                "omegaconf",
                description=_("Установка omegaconf...", "Installing omegaconf...")
            )
            if not success:
                update_status(_("Ошибка при установке omegaconf", "Error installing omegaconf"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            update_progress(70)

            package_url = None
            desc = ""
            if self.parent.provider in ["NVIDIA"]:
                package_url = "tts_with_rvc"
                desc = _("Установка основной библиотеки tts-with-rvc (NVIDIA)...", "Installing main library tts-with-rvc (NVIDIA)...")
            elif self.parent.provider in ["AMD"]:
                package_url = "tts_with_rvc_onnx[dml]"
                desc = _("Установка основной библиотеки tts-with-rvc (AMD)...", "Installing main library tts-with-rvc (AMD)...")
            else:
                update_log(_(f"Ошибка: не найдена подходящая видеокарта: {self.parent.provider}", f"Error: suitable graphics card not found: {self.parent.provider}"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            success = installer.install_package(package_url, description=desc)

            if not success:
                update_status(_("Ошибка при установке tts-with-rvc", "Error installing tts-with-rvc"))
                QTimer.singleShot(5000, progress_window.close)
                return False

            libs_path_abs = os.path.abspath("Lib")
            update_progress(95)
            update_status(_("Применение патчей...", "Applying patches..."))
            config_path = os.path.join(libs_path_abs, "fairseq", "dataclass", "configs.py")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        source = f.read()
                    patched_source = re.sub(r"metadata=\{(.*?)help:", r'metadata={\1"help":', source)
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(patched_source)
                    update_log(_("Патч успешно применен к configs.py", "Patch successfully applied to configs.py"))
                except Exception as e:
                    update_log(_(f"Ошибка при патче configs.py: {e}", f"Error patching configs.py: {e}"))
            
            update_progress(100)
            update_status(_("Установка успешно завершена!", "Installation successful!"))
            
            self._load_module()
            
            QTimer.singleShot(3000, progress_window.close)
            return True
        except Exception as e:
            logger.error(f"Ошибка при установке Edge-TTS + RVC: {e}", exc_info=True)
            if gui_elements and gui_elements["window"]:
                gui_elements["window"].close()
            return False

    def uninstall(self, model_id) -> bool:
        return self.parent._uninstall_component("EdgeTTS+RVC", "tts-with-rvc")

    def cleanup_state(self):
        super().cleanup_state()
        self.current_tts_rvc = None
        self.current_silero_model = None
        self.tts_rvc_module = None
        logger.info(f"Состояние для обработчика EdgeTTS/Silero+RVC сброшено.")

    def initialize(self, init: bool = False) -> bool:
        # Эта функция теперь вызывается с конкретным model_id, который определяет режим работы
        current_mode = self.parent.current_model_id
        logger.info(f"Запрос на инициализацию обработчика в режиме: '{current_mode}'")

        # Шаг 1: Инициализация базового RVC, если его еще нет
        if self.current_tts_rvc is None:
            logger.info("Инициализация базового компонента RVC...")
            if self.tts_rvc_module is None:
                logger.error("Модуль tts_with_rvc не установлен.")
                return False
            
            settings = self.parent.load_model_settings(current_mode)
            device = settings.get("device", "cuda:0" if self.parent.provider == "NVIDIA" else "dml")
            f0_method = settings.get("f0method", "rmvpe" if self.parent.provider == "NVIDIA" else "pm")
            
            is_nvidia = self.parent.provider in ["NVIDIA"]
            model_ext = 'pth' if is_nvidia else 'onnx'
            default_model_path = os.path.join("Models", f"Mila.{model_ext}")
            
            model_path_to_use = self.parent.pth_path if self.parent.pth_path and os.path.exists(self.parent.pth_path) else default_model_path
            if not os.path.exists(model_path_to_use):
                logger.error(f"Не найден файл RVC модели: {model_path_to_use}")
                return False

            self.current_tts_rvc = self.tts_rvc_module(model_path=model_path_to_use, device=device, f0_method=f0_method)
            logger.info("Базовый компонент RVC инициализирован.")
        
        # Обновляем голос EdgeTTS в RVC в любом случае
        if self.parent.voice_language == "ru":
            self.current_tts_rvc.set_voice("ru-RU-SvetlanaNeural")
        else:
            self.current_tts_rvc.set_voice("en-US-MichelleNeural")

        # Шаг 2: Управление компонентом Silero в зависимости от режима
        if current_mode == "low+":
            if self.current_silero_model is None:
                logger.info("Требуется режим 'low+', инициализация компонента Silero...")
                try:
                    import torch
                    settings = self.parent.load_model_settings(current_mode)
                    silero_device = settings.get("silero_device", "cuda" if self.parent.provider == "NVIDIA" else "cpu")
                    self.current_silero_sample_rate = int(settings.get("silero_sample_rate", 48000))
                    language = 'en' if self.parent.voice_language == 'en' else 'ru'
                    model_id_silero = 'v3_en' if language == 'en' else 'v4_ru'
                    
                    logger.info(f"Загрузка модели Silero ({language}/{model_id_silero})...")
                    model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models', model='silero_tts', language=language, speaker=model_id_silero, trust_repo=True)
                    model.to(silero_device)
                    self.current_silero_model = model
                    logger.info("Компонент Silero для 'low+' успешно инициализирован.")
                except Exception as e:
                    logger.error(f"Ошибка инициализации компонента Silero: {e}", exc_info=True)
                    return False
        else: # Для режима "low" или любого другого, убедимся, что Silero выгружен
            if self.current_silero_model is not None:
                logger.info("Переключение в режим без Silero. Выгрузка компонента Silero...")
                self.current_silero_model = None
                import gc
                gc.collect()

        # Шаг 3: Установка флага и тестовый прогон
        # Проверяем, что все необходимые компоненты на месте
        is_ready = self.current_tts_rvc is not None
        if current_mode == "low+":
            is_ready = is_ready and self.current_silero_model is not None

        if not is_ready:
            logger.error(f"Не все компоненты для модели '{current_mode}' удалось инициализировать.")
            self.initialized = False
            return False

        # Если мы дошли сюда, значит все нужные компоненты загружены.
        # Запускаем тестовый прогон только если модель еще не была помечена как инициализированная.
        if not self.initialized and init:
            self.initialized = True # Ставим флаг до прогона
            init_text = f"Инициализация модели {current_mode}" if self.parent.voice_language == "ru" else f"{current_mode} Model Initialization"
            logger.info(f"Выполнение тестового прогона для {current_mode}...")
            try:
                main_loop = self.parent.parent.loop
                if not main_loop or not main_loop.is_running():
                    raise RuntimeError("Главный цикл событий asyncio недоступен.")
                
                future = asyncio.run_coroutine_threadsafe(self.voiceover(init_text), main_loop)
                result = future.result(timeout=3600)
                logger.info(f"Тестовый прогон для {current_mode} успешно завершен.")
            except Exception as e:
                logger.error(f"Ошибка во время тестового прогона модели {current_mode}: {e}", exc_info=True)
                self.initialized = False # Сбрасываем флаг в случае ошибки
                return False
        
        self.initialized = True
        return True

    async def voiceover(self, text: str, character: Optional[Any] = None, **kwargs) -> Optional[str]:
        current_mode = self.parent.current_model_id
        if not self.initialized:
            raise Exception(f"Обработчик не инициализирован для режима '{current_mode}'.")
            
        if current_mode == "low":
            return await self._voiceover_edge_tts_rvc(text, **kwargs)
        elif current_mode == "low+":
            return await self._voiceover_silero_rvc(text, character)
        else:
            raise ValueError(f"Обработчик вызван с неизвестным режимом: {current_mode}")

    async def apply_rvc_to_file(self, filepath: str, 
                               pitch: float = 0,
                               index_rate: float = 0.75,
                               protect: float = 0.33,
                               filter_radius: int = 3,
                               rms_mix_rate: float = 0.5,
                               is_half: bool = True,
                               f0method: Optional[str] = None,
                               use_index_file: bool = True,
                               original_model_id: Optional[str] = None) -> Optional[str]:
        """
        Применяет RVC к существующему аудиофайлу.
        
        Параметры:
        - filepath: путь к входному аудиофайлу
        - pitch: изменение высоты тона (-24 до 24)
        - index_rate: коэффициент использования индексного файла (0.0 до 1.0)
        - protect: защита консонант от изменений (0.0 до 0.5)
        - filter_radius: радиус медианного фильтра (0 до 7)
        - rms_mix_rate: коэффициент смешивания RMS (0.0 до 1.0)
        - is_half: использовать половинную точность (только для NVIDIA)
        - f0method: метод извлечения основного тона (rmvpe, pm, harvest, crepe)
        - use_index_file: использовать индексный файл если доступен
        - original_model_id: ID исходной модели для конфигурации (устарело)
        """
        if not self.initialized:
            logger.info("Инициализация RVC компонента на лету...")
            if not self.initialize(init=False):
                logger.error("Не удалось инициализировать RVC компонент.")
                return None

        logger.info(f"Вызов RVC для файла: {filepath}")
        
        try:
            # Подготовка параметров инференса
            inference_params = {
                "pitch": pitch,
                "index_rate": index_rate,
                "protect": protect,
                "filter_radius": filter_radius,
                "rms_mix_rate": rms_mix_rate
            }
            
            if self.parent.provider == "NVIDIA":
                inference_params["is_half"] = is_half
                
            if f0method:
                inference_params["f0method"] = f0method
            
            # Установка индексного файла
            if use_index_file and self.parent.index_path and os.path.exists(self.parent.index_path):
                self.current_tts_rvc.set_index_path(self.parent.index_path)
            else:
                self.current_tts_rvc.set_index_path("")
            
            # Обновление модели если необходимо
            if os.path.abspath(self.parent.pth_path) != os.path.abspath(self.current_tts_rvc.current_model):
                if self.parent.provider in ["NVIDIA"]:
                    self.current_tts_rvc.current_model = self.parent.pth_path
                elif self.parent.provider in ["AMD"]:
                    self.current_tts_rvc.current_model = self.parent.pth_path
            
            # Применение RVC
            output_file_rvc = self.current_tts_rvc.voiceover_file(input_path=filepath, **inference_params)
            
            if not output_file_rvc or not os.path.exists(output_file_rvc) or os.path.getsize(output_file_rvc) == 0:
                return None
            
            # Конвертация в стерео
            stereo_output_file = output_file_rvc.replace(".wav", "_stereo.wav")
            converted_file = self.parent.convert_wav_to_stereo(
                output_file_rvc, 
                stereo_output_file, 
                atempo=1.0, 
                pitch=(4 if self.parent.current_character_name == 'ShorthairMita' and self.parent.provider in ['AMD'] else 0)
            )

            if converted_file and os.path.exists(converted_file):
                final_output_path = stereo_output_file
                try: os.remove(output_file_rvc)
                except OSError: pass
            else:
                final_output_path = output_file_rvc
            
            return final_output_path
            
        except Exception as error:
            traceback.print_exc()
            logger.info(f"Ошибка при применении RVC к файлу: {error}")
            return None

    # def _get_fsprvc_params(self, settings: dict) -> dict:
    #     """
    #     Получает параметры для FSP+RVC модели.
    #     Эта функция закомментирована для напоминания о FSP+RVC параметрах.
    #     
    #     Параметры FSP+RVC из настроек:
    #     - fsprvc_rvc_pitch: высота тона для RVC
    #     - fsprvc_index_rate: коэффициент использования индекса 
    #     - fsprvc_protect: защита консонант
    #     - fsprvc_filter_radius: радиус медианного фильтра
    #     - fsprvc_rvc_rms_mix_rate: коэффициент смешивания RMS
    #     - fsprvc_is_half: использовать половинную точность
    #     - fsprvc_f0method: метод извлечения F0
    #     - fsprvc_use_index_file: использовать индексный файл
    #     """
    #     return {
    #         "pitch": float(settings.get("fsprvc_rvc_pitch", 0)),
    #         "index_rate": float(settings.get("fsprvc_index_rate", 0.75)),
    #         "protect": float(settings.get("fsprvc_protect", 0.33)),
    #         "filter_radius": int(settings.get("fsprvc_filter_radius", 3)),
    #         "rms_mix_rate": float(settings.get("fsprvc_rvc_rms_mix_rate", 0.5)),
    #         "is_half": settings.get("fsprvc_is_half", "True").lower() == "true",
    #         "f0method": settings.get("fsprvc_f0method", None),
    #         "use_index_file": settings.get("fsprvc_use_index_file", True)
    #     }

    async def _voiceover_edge_tts_rvc(self, text, TEST_WITH_DONE_AUDIO: str = None, settings_model_id: Optional[str] = None):
        if self.current_tts_rvc is None:
            raise Exception("Компонент RVC не инициализирован.")
        try:
            config_id = settings_model_id if settings_model_id else self.parent.current_model_id
            settings = self.parent.load_model_settings(config_id)
            logger.info(f"RVC использует конфигурацию от модели: '{config_id}'")

            # Получаем параметры из настроек
            pitch = float(settings.get("pitch", 0))
            if self.parent.current_character_name == "Player" and config_id != "medium+low":
                pitch = -12
            
            index_rate = float(settings.get("index_rate", 0.75))
            protect = float(settings.get("protect", 0.33))
            filter_radius = int(settings.get("filter_radius", 3))
            rms_mix_rate = float(settings.get("rms_mix_rate", 0.5))
            is_half = settings.get("is_half", "True").lower() == "true"
            use_index_file = settings.get("use_index_file", True)
            f0method_override = settings.get("f0method", None)
            tts_rate = int(settings.get("tts_rate", 0)) if config_id != "medium+low" else 0

            if use_index_file and self.parent.index_path and os.path.exists(self.parent.index_path):
                self.current_tts_rvc.set_index_path(self.parent.index_path)
            else:
                self.current_tts_rvc.set_index_path("")
            
            if self.parent.provider in ["NVIDIA"]:
                inference_params = {"pitch": pitch, "index_rate": index_rate, "protect": protect, "filter_radius": filter_radius, "rms_mix_rate": rms_mix_rate, "is_half": is_half}
            else:
                inference_params = {"pitch": pitch, "index_rate": index_rate, "protect": protect, "filter_radius": filter_radius, "rms_mix_rate": rms_mix_rate}
            if f0method_override:
                inference_params["f0method"] = f0method_override
            
            if os.path.abspath(self.parent.pth_path) != os.path.abspath(self.current_tts_rvc.current_model):
                if self.parent.provider in ["NVIDIA"]:
                    self.current_tts_rvc.current_model = self.parent.pth_path
                elif self.parent.provider in ["AMD"]:
                    self.current_tts_rvc.current_model = self.parent.pth_path

            if not TEST_WITH_DONE_AUDIO:
                inference_params["tts_rate"] = tts_rate
                output_file_rvc = self.current_tts_rvc(text=text, **inference_params)
            else:
                output_file_rvc = self.current_tts_rvc.voiceover_file(input_path=TEST_WITH_DONE_AUDIO, **inference_params)

            if not output_file_rvc or not os.path.exists(output_file_rvc) or os.path.getsize(output_file_rvc) == 0:
                return None
            
            stereo_output_file = output_file_rvc.replace(".wav", "_stereo.wav")
            converted_file = self.parent.convert_wav_to_stereo(output_file_rvc, stereo_output_file, atempo=1.0, pitch=(4 if self.parent.current_character_name == 'ShorthairMita' and self.parent.provider in ['AMD'] else 0))

            if converted_file and os.path.exists(converted_file):
                final_output_path = stereo_output_file
                try: os.remove(output_file_rvc)
                except OSError: pass
            else:
                final_output_path = output_file_rvc
            
            if self.parent.parent.ConnectedToGame and TEST_WITH_DONE_AUDIO is None:
                self.parent.parent.patch_to_sound_file = final_output_path
            return final_output_path
        except Exception as error:
            traceback.print_exc()
            logger.info(f"Ошибка при создании озвучки с Edge-TTS + RVC: {error}")
            return None

    def _preprocess_text_to_ssml(self, text: str):
        lang = self.parent.voice_language
        defaults = {'en': {'pitch': 6, 'speaker': "en_88"}, 'ru': {'pitch': 2, 'speaker': "kseniya"}}
        lang_defaults = defaults.get(lang, defaults['en'])
        char_params = {
            'en': {"CappieMita": (6, "en_26"), "CrazyMita": (6, "en_60"), "GhostMita": (6, "en_33"), "Mila": (6, "en_88"), "MitaKind": (3, "en_33"), "ShorthairMita": (6, "en_60"), "SleepyMita": (6, "en_33"), "TinyMita": (2, "en_60"), "Player": (0, "en_27")},
            'ru': {"CappieMita": (6, "kseniya"), "MitaKind": (1, "kseniya"), "ShorthairMita": (2, "kseniya"), "CrazyMita": (2, "kseniya"), "Mila": (2, "kseniya"), "TinyMita": (-3, "baya"), "SleepyMita": (2, "baya"), "GhostMita": (1, "baya"), "Player": (0, "aidar")}
        }
        character_rvc_pitch, character_speaker = lang_defaults['pitch'], lang_defaults['speaker']
        character_short_name = self.parent.current_character_name
        current_lang_params = char_params.get(lang, char_params['en'])
        if specific_params := current_lang_params.get(character_short_name):
            character_rvc_pitch, character_speaker = specific_params
        
        text = escape(re.sub(r'<[^>]*>', '', text)).replace("Mita", "M+ita").replace("Mila", "M+ila").replace("mita", "m+ita").replace("mila", "m+ila")
        parts = re.split(r'([.!?]+[^A-Za-zА-Яа-я0-9_]*)(\s+)', text.strip())
        processed_text = ""
        i = 0
        while i < len(parts):
            if text_part := parts[i]: processed_text += text_part
            if i + 2 < len(parts):
                if punctuation_part := parts[i+1]: processed_text += punctuation_part
                if (whitespace_part := parts[i+2]) and i + 3 < len(parts) and parts[i+3]: processed_text += f' <break time="300ms"/> '
                elif whitespace_part: processed_text += whitespace_part
            i += 3
        ssml_content = processed_text.strip()
        ssml_output = f'<speak><p>{ssml_content}</p></speak>' if ssml_content else '<speak></speak>'
        return ssml_output, character_rvc_pitch, character_speaker
    
    async def _voiceover_silero_rvc(self, text, character=None):
        if self.current_silero_model is None or self.current_tts_rvc is None:
            raise Exception("Компоненты Silero или RVC не инициализированы для режима low+.")
        
        self.parent.current_character = character if character is not None else getattr(self.parent, 'current_character', None)
        temp_wav = None
        try:
            ssml_text, character_base_rvc_pitch, character_speaker = self._preprocess_text_to_ssml(text)
            settings = self.parent.load_model_settings('low+')
            
            audio_tensor = self.current_silero_model.apply_tts(
                ssml_text=ssml_text, speaker=character_speaker, sample_rate=self.current_silero_sample_rate,
                put_accent=settings.get("silero_put_accent", True), put_yo=settings.get("silero_put_yo", True)
            )
            
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_wav_file:
                temp_wav = temp_wav_file.name
            sf.write(temp_wav, audio_tensor.cpu().numpy(), self.current_silero_sample_rate)
            
            if not os.path.exists(temp_wav) or os.path.getsize(temp_wav) == 0:
                 return None

            # Подготовка параметров RVC для Silero
            base_rvc_pitch_from_settings = float(settings.get("silero_rvc_pitch", 6))
            final_rvc_pitch = base_rvc_pitch_from_settings - (6 - character_base_rvc_pitch)

            # Настройка модели RVC для персонажа
            is_nvidia = self.parent.provider in ["NVIDIA"]
            model_ext = 'pth' if is_nvidia else 'onnx'
            rvc_model_short_name = str(getattr(character, 'short_name', "Mila"))
            self.parent.pth_path = os.path.join(self.parent.clone_voice_folder, f"{rvc_model_short_name}.{model_ext}")
            self.parent.index_path = os.path.join(self.parent.clone_voice_folder, f"{rvc_model_short_name}.index")
            if not os.path.exists(self.parent.pth_path): 
                raise Exception(f"Файл модели RVC не найден: {self.parent.pth_path}")

            if os.path.abspath(self.parent.pth_path) != os.path.abspath(getattr(self.current_tts_rvc, 'current_model', '')):
                logger.info(f"Смена RVC модели на: {self.parent.pth_path}")
                if self.parent.provider in ["NVIDIA"]:
                    self.current_tts_rvc.current_model = self.parent.pth_path
                elif self.parent.provider in ["AMD"]:
                    if hasattr(self.current_tts_rvc, 'set_model'):
                        self.current_tts_rvc.set_model(self.parent.pth_path)
                    else:
                        self.current_tts_rvc.current_model = self.parent.pth_path
                        logger.warning("Метод 'set_model' не найден, используется прямое присваивание (может не работать на AMD).")

            # Применение RVC через общую функцию
            final_output_path = await self.apply_rvc_to_file(
                filepath=temp_wav,
                pitch=final_rvc_pitch,
                index_rate=float(settings.get("silero_rvc_index_rate", 0.75)),
                protect=float(settings.get("silero_rvc_protect", 0.33)),
                filter_radius=int(settings.get("silero_rvc_filter_radius", 3)),
                rms_mix_rate=float(settings.get("silero_rvc_rms_mix_rate", 0.5)),
                is_half=settings.get("silero_rvc_is_half", "True").lower() == "true" if self.parent.provider == "NVIDIA" else True,
                f0method=settings.get("silero_rvc_f0method", None),
                use_index_file=settings.get("use_index_file", True)
            )
            
            if hasattr(self.parent.parent, 'ConnectedToGame') and self.parent.parent.ConnectedToGame:
                self.parent.parent.patch_to_sound_file = final_output_path
            
            return final_output_path
            
        except Exception as error:
            traceback.print_exc()
            logger.info(f"Ошибка при создании озвучки с Silero + RVC: {error}")
            return None
        finally:
            if temp_wav and os.path.exists(temp_wav):
                try: os.remove(temp_wav)
                except OSError: pass