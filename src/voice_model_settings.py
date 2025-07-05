# voice_model_settings.py

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
                             QFrame, QScrollArea, QLineEdit, QComboBox, QCheckBox,
                             QSizePolicy, QMessageBox, QApplication, QToolTip)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QEvent, QPoint
from PyQt6.QtGui import QFont, QCursor

import os
import platform
import time
import copy
import json
import threading
from docs import DocsManager
from main_logger import logger
import traceback

from settings_manager import SettingsManager
from pyqt_styles.voice_model_styles import get_stylesheet

from utils import getTranslationVariant as _

model_descriptions = {
    "low": "Быстрая модель, комбинация Edge-TTS для генерации речи и RVC для преобразования голоса. Низкие требования.",
    "low+": "Комбинация Silero TTS для генерации речи и RVC для преобразования голоса. Требования схожи с low.",
    "medium": "Модель Fish Speech для генерации речи с хорошим качеством. Требует больше ресурсов.",
    "medium+": "Скомпилированная на видеокарту версия Fish Speech. Требует больше места.",
    "medium+low": "Комбинация Fish Speech+ и RVC для высококачественного преобразования голоса.",
    "high": "Лучшая эмоциональная модель. Дифузионная модель, так что самая требовательная к видеокарте.",
    "high+low": "Лучшая эмоциональная модель. Дифузионная модель, так что самая требовательная к видеокарте."
}

model_descriptions_en = {
    "low": "Fast model; a combination of Edge-TTS for speech generation and RVC for voice conversion. Low requirements.",
    "low+": "Combination of Silero TTS for speech generation and RVC for voice conversion. Requirements similar to the 'low' model.",
    "medium": "Fish Speech model for speech generation with good quality. Requires more resources.",
    "medium+": "GPU-compiled version of Fish Speech. Requires more disk space.",
    "medium+low": "Combination of Fish Speech+ and RVC for high-quality voice conversion.",
    "high": "Best emotional model. A diffusion model, therefore the most GPU-demanding.",
    "high+low": "Best emotional model with RVC. A diffusion model, therefore the most GPU-demanding."
}

setting_descriptions = {
    "device": "Устройство для вычислений (GPU или CPU). 'cuda:0' - первая GPU NVIDIA, 'cpu' - центральный процессор, 'mps:0' - GPU Apple Silicon.",
    "pitch": "Изменение высоты голоса в полутонах. Положительные значения - выше, отрицательные - ниже. 0 - без изменений.",
    "is_half": "Использовать вычисления с половинной точностью (float16). Ускоряет работу на совместимых GPU (NVIDIA RTX и новее) и экономит видеопамять, может незначительно повлиять на качество.",
    "output_gain": "Усиление громкости финального аудиофайла. Значение 1.0 - без изменений, <1 тише, >1 громче. Полезно для нормализации громкости разных голосов.",
    "f0method": "[RVC] Алгоритм извлечения основного тона (F0). Определяет высоту голоса. 'rmvpe' и 'crepe' точные, но медленные. 'pm', 'harvest' быстрее. Влияет на естественность интонаций.",
    "use_index_file": "[RVC] Использовать файл .index для улучшения соответствия тембра голоса модели. Отключение может быть полезно, если индексный файл низкого качества или вызывает артефакты.",
    "index_rate": "[RVC] Степень использования индексного файла (.index) для сохранения тембра голоса RVC (0 до 1). Выше значение = больше похоже на голос из модели, но может добавить артефакты, если индекс некачественный.",
    "filter_radius": "[RVC] Радиус медианного фильтра для сглаживания кривой F0 (высоты тона). Убирает резкие скачки, делает речь более плавной. Рекомендуется значение >= 3.",
    "rms_mix_rate": "[RVC] Степень смешивания RMS (громкости) исходного аудио (из TTS/FSP) и результата RVC (0 до 1). 0 = полностью громкость RVC, 1 = полностью громкость оригинала. Помогает сохранить исходную динамику речи.",
    "protect": "[RVC] Защита глухих согласных (ш, щ, с, ...) от искажения высотой тона (0 до 0.5). Меньшие значения обеспечивают большую защиту (согласные звучат чище), но могут немного повлиять на интонацию гласных рядом. Рекомендуется 0.3-0.4.",
    "tts_rate": "[EdgeTTS] Изменение скорости речи базового синтезатора Edge-TTS (до RVC) в процентах. 0 - стандартная скорость.",
    "tts_volume": "[EdgeTTS] Изменение громкости речи базового синтезатора Edge-TTS (до RVC) в процентах. 0 - стандартная громкость.",
    
    "seed": "Сид для озвучки.",
    
    "silero_device": "[Silero] Устройство для генерации речи Silero (CPU или GPU).",
    "silero_sample_rate": "[Silero] Частота дискретизации для генерации речи Silero.", 
    "silero_put_accent": "[Silero] Автоматическая расстановка ударений.", 
    "silero_put_yo": "[Silero] Автоматическая замена 'е' на 'ё'.", 

    "half": "[FS/FSP] Использовать FP16 (половинную точность). Рекомендуется для скорости и экономии памяти на GPU.",
    "temperature": "[FS/FSP] Температура сэмплирования (>0). Контролирует случайность/разнообразие генерируемой речи. Выше = разнообразнее, но больше ошибок. Ниже = стабильнее.",
    "top_p": "[FS/FSP] Ядерное сэмплирование (Top-P, 0-1). Ограничивает выбор следующего токена только наиболее вероятными вариантами. Уменьшает вероятность генерации 'бреда'.",
    "repetition_penalty": "[FS/FSP] Штраф за повторение токенов (>1). Предотвращает зацикливание модели на одних и тех же словах/звуках. 1.0 - нет штрафа.",
    "chunk_length": "[FS/FSP] Размер чанка обработки текста (в токенах). Влияет на использование памяти и длину контекста, который модель 'видит' одновременно.",
    "max_new_tokens": "[FS/FSP] Максимальное количество генерируемых токенов за один шаг. Ограничивает длину аудиофрагмента, генерируемого за раз.",
    "compile_model": "[FSP] Использовать torch.compile() для JIT-компиляции модели. Значительно ускоряет выполнение на GPU после первого запуска, но требует доп. установки и время на компиляцию при старте.",
    "fsprvc_fsp_device": "[FSP+RVC][FSP] Устройство для части Fish Speech+.",
    "fsprvc_fsp_half": "[FSP+RVC][FSP] Half-precision для части Fish Speech+.",
    "fsprvc_fsp_temperature": "[FSP+RVC][FSP] Температура для части Fish Speech+.",
    "fsprvc_fsp_top_p": "[FSP+RVC][FSP] Top-P для части Fish Speech+.",
    "fsprvc_fsp_repetition_penalty": "[FSP+RVC][FSP] Штраф повторений для части Fish Speech+.",
    "fsprvc_fsp_chunk_length": "[FSP+RVC][FSP] Размер чанка для части Fish Speech+.",
    "fsprvc_fsp_max_tokens": "[FSP+RVC][FSP] Макс. токены для части Fish Speech+.",
    "fsprvc_fsp_seed": "[FSP+RVC][FSP] Сид для озвучки.",
    "fsprvc_rvc_device": "[FSP+RVC][RVC] Устройство для части RVC.",
    "fsprvc_is_half": "[FSP+RVC][RVC] Half-precision для части RVC.",
    "fsprvc_f0method": "[FSP+RVC][RVC] Метод F0 для части RVC.",
    "fsprvc_rvc_pitch": "[FSP+RVC][RVC] Высота голоса для части RVC.",
    "fsprvc_use_index_file": "[FSP+RVC][RVC] Использовать файл .index для улучшения соответствия тембра голоса модели. Отключение может быть полезно, если индексный файл низкого качества или вызывает артефакты.",
    "fsprvc_index_rate": "[FSP+RVC][RVC] Соотношение индекса для части RVC.",
    "fsprvc_protect": "[FSP+RVC][RVC] Защита согласных для части RVC.",
    "fsprvc_output_gain": "[FSP+RVC][RVC] Громкость (gain) для части RVC.",
    "fsprvc_filter_radius": "[FSP+RVC][RVC] Радиус фильтра F0 для части RVC.",
    "fsprvc_rvc_rms_mix_rate": "[FSP+RVC][RVC] Смешивание RMS для части RVC.",


    "speed": "[F5-TTS] Скорость генерируемой речи. 1.0 - нормальная скорость, >1.0 - быстрее, <1.0 - медленнее.",
    "remove_silence": "[F5-TTS] Автоматически удалять тишину в начале и конце сгенерированного аудио.",
    "nfe_step": "[F5-TTS] Количество шагов диффузии. Больше = лучше качество, но медленнее. Меньше = быстрее, но может быть хуже. (Рекомендуется: 3-10)",
    "cfg_strength": "[F5-TTS] Сила бесклассификаторного управления (CFG). Контролирует, насколько сильно генерация следует за референсным аудио. 0 - отключено. (Рекомендуется: 0.7)",
    "sway_sampling_coef": "[F5-TTS] Коэффициент сэмплирования 'Sway'. Добавляет вариативности в генерацию. 0 - отключено. (Рекомендуется: 0.0)",
    "target_rms": "[F5-TTS] Целевая громкость (RMS) для нормализации аудио. -1 отключает нормализацию. (Рекомендуется: -1)",
    "cross_fade_duration": "[F5-TTS] Длительность кроссфейда (в секундах) между аудио-чанками. (Рекомендуется: 0.015)",
    "fix_duration": "[F5-TTS] Фиксировать длительность фонем. Может улучшить стабильность, но снизить естественность. (Рекомендуется: False)",

    "f5rvc_f5_device": "[F5+RVC][F5] Устройство для части F5-TTS.",
    "f5rvc_f5_speed": "[F5+RVC][F5] Скорость речи для части F5-TTS.",
    "f5rvc_f5_nfe_step": "[F5+RVC][F5] Количество шагов диффузии для части F5-TTS.",
    "f5rvc_f5_remove_silence": "[F5+RVC][F5] Удаление тишины для части F5-TTS.",
    "f5rvc_f5_seed": "[F5+RVC][F5] Сид для озвучки.",
    "f5rvc_rvc_pitch": "[F5+RVC][RVC] Высота голоса для части RVC.",
    "f5rvc_index_rate": "[F5+RVC][RVC] Соотношение индекса для части RVC.",
    "f5rvc_protect": "[F5+RVC][RVC] Защита согласных для части RVC.",
    "f5rvc_filter_radius": "[F5+RVC][RVC] Радиус фильтра F0 для части RVC.",
    "f5rvc_rvc_rms_mix_rate": "[F5+RVC][RVC] Смешивание RMS для части RVC.",
    "f5rvc_is_half": "[F5+RVC][RVC] Half-precision для части RVC.",
    "f5rvc_f0method": "[F5+RVC][RVC] Метод F0 для части RVC.",
    "f5rvc_use_index_file": "[F5+RVC][RVC] Использовать файл .index для улучшения соответствия тембра голоса модели.",

    "tmp_directory": "Папка для временных файлов, создаваемых в процессе работы (например, промежуточные аудиофайлы).",
    "verbose": "Включить вывод подробной отладочной информации в консоль для диагностики проблем.",
    "cuda_toolkit": "Наличие установленного CUDA Toolkit от NVIDIA. Необходимо для некоторых функций (например, torch.compile) и работы с GPU NVIDIA.",
    "windows_sdk": "Наличие установленного Windows SDK. Может требоваться для компиляции некоторых зависимостей Python.",
}

setting_descriptions_en = {
    "device": "Device for computation (GPU or CPU). 'cuda:0' - first NVIDIA GPU, 'cpu' - central processor, 'mps:0' - Apple Silicon GPU.",
    "pitch": "Voice pitch change in semitones. Positive values - higher, negative - lower. 0 - no change.",
    "is_half": "Use half-precision computations (float16). Speeds up work on compatible GPUs (NVIDIA RTX and newer) and saves VRAM, may slightly affect quality.",
    "output_gain": "Volume gain for the final audio file. Value 1.0 - no change, <1 quieter, >1 louder. Useful for normalizing the volume of different voices.",
    "f0method": "[RVC] Fundamental frequency (F0) extraction algorithm. Determines voice pitch. 'rmvpe' and 'crepe' are accurate but slow. 'pm', 'harvest' are faster. Affects the naturalness of intonations.",
    "use_index_file": "[RVC] Use the .index file to improve the model's voice timbre matching. Disabling may be useful if the index file is low quality or causes artifacts.",
    "index_rate": "[RVC] Degree of using the index file (.index) to preserve the RVC voice timbre (0 to 1). Higher value = more similar to the model's voice, but may add artifacts if the index is poor quality.",
    "filter_radius": "[RVC] Radius of the median filter for smoothing the F0 curve (pitch). Removes sharp jumps, makes speech smoother. Recommended value >= 3.",
    "rms_mix_rate": "[RVC] Degree of mixing RMS (volume) of the source audio (from TTS/FSP) and the RVC result (0 to 1). 0 = fully RVC volume, 1 = fully original volume. Helps preserve the original speech dynamics.",
    "protect": "[RVC] Protection of voiceless consonants (sh, shch, s, ...) from pitch distortion (0 to 0.5). Lower values provide more protection (consonants sound cleaner), but may slightly affect the intonation of nearby vowels. Recommended 0.3-0.4.",
    "tts_rate": "[EdgeTTS] Change the speech rate of the base Edge-TTS synthesizer (before RVC) in percent. 0 - standard speed.",
    "tts_volume": "[EdgeTTS] Change the speech volume of the base Edge-TTS synthesizer (before RVC) in percent. 0 - standard volume.",
    "silero_device": "[Silero] Device for Silero speech generation (CPU or GPU).",
    "silero_sample_rate": "[Silero] Sample rate for Silero speech generation.",
    "silero_put_accent": "[Silero] Automatic stress placement.",
    "silero_put_yo": "[Silero] Automatic replacement of 'e' with 'yo'.",
    "half": "[FS/FSP] Use FP16 (half-precision). Recommended for speed and memory saving on GPU.",
    "temperature": "[FS/FSP] Sampling temperature (>0). Controls the randomness/diversity of generated speech. Higher = more diverse, but more errors. Lower = more stable.",
    "top_p": "[FS/FSP] Nucleus sampling (Top-P, 0-1). Limits the choice of the next token to only the most likely options. Reduces the probability of generating 'nonsense'.",
    "repetition_penalty": "[FS/FSP] Penalty for repeating tokens (>1). Prevents the model from looping on the same words/sounds. 1.0 - no penalty.",
    "chunk_length": "[FS/FSP] Text processing chunk size (in tokens). Affects memory usage and the length of the context the model 'sees' simultaneously.",
    "max_new_tokens": "[FS/FSP] Maximum number of generated tokens per step. Limits the length of the audio fragment generated at once.",
    "compile_model": "[FSP] Use torch.compile() for JIT compilation of the model. Significantly speeds up execution on GPU after the first run, but requires additional installation and compilation time at startup.",
    "fsprvc_fsp_device": "[FSP+RVC][FSP] Device for the Fish Speech+ part.",
    "fsprvc_fsp_half": "[FSP+RVC][FSP] Half-precision for the Fish Speech+ part.",
    "fsprvc_fsp_temperature": "[FSP+RVC][FSP] Temperature for the Fish Speech+ part.",
    "fsprvc_fsp_top_p": "[FSP+RVC][FSP] Top-P for the Fish Speech+ part.",
    "fsprvc_fsp_repetition_penalty": "[FSP+RVC][FSP] Repetition penalty for the Fish Speech+ part.",
    "fsprvc_fsp_chunk_length": "[FSP+RVC][FSP] Chunk size for the Fish Speech+ part.",
    "fsprvc_fsp_max_tokens": "[FSP+RVC][FSP] Max tokens for the Fish Speech+ part.",
    "fsprvc_rvc_device": "[FSP+RVC][RVC] Device for the RVC part.",
    "fsprvc_is_half": "[FSP+RVC][RVC] Half-precision for the RVC part.",
    "fsprvc_f0method": "[FSP+RVC][RVC] F0 method for the RVC part.",
    "fsprvc_rvc_pitch": "[FSP+RVC][RVC] Voice pitch for the RVC part.",
    "fsprvc_use_index_file": "[FSP+RVC][RVC] Use the .index file to improve the model's voice timbre matching. Disabling may be useful if the index file is low quality or causes artifacts.",
    "fsprvc_index_rate": "[FSP+RVC][RVC] Index rate for the RVC part.",
    "fsprvc_protect": "[FSP+RVC][RVC] Consonant protection for the RVC part.",
    "fsprvc_output_gain": "[FSP+RVC][RVC] Volume (gain) for the RVC part.",
    "fsprvc_filter_radius": "[FSP+RVC][RVC] F0 filter radius for the RVC part.",
    "fsprvc_rvc_rms_mix_rate": "[FSP+RVC][RVC] RMS mixing for the RVC part.",

    "speed": "[F5-TTS] Speed of the generated speech. 1.0 is normal speed, >1.0 is faster, <1.0 is slower.",
    "remove_silence": "[F5-TTS] Automatically remove silence from the beginning and end of the generated audio.",
    "nfe_step": "[F5-TTS] Number of diffusion steps. More = better quality, but slower. Less = faster, but may be worse. (Recommended: 3-10)",
    "cfg_strength": "[F5-TTS] Classifier-Free Guidance (CFG) strength. Controls how strongly the generation follows the reference audio. 0 - disabled. (Recommended: 0.7)",
    "sway_sampling_coef": "[F5-TTS] 'Sway' sampling coefficient. Adds variability to the generation. 0 - disabled. (Recommended: 0.0)",
    "target_rms": "[F5-TTS] Target loudness (RMS) for audio normalization. -1 disables normalization. (Recommended: -1)",
    "cross_fade_duration": "[F5-TTS] Crossfade duration (in seconds) between audio chunks. (Recommended: 0.015)",
    "fix_duration": "[F5-TTS] Fix phoneme duration. May improve stability but reduce naturalness. (Recommended: False)",

    "f5rvc_f5_device": "[F5+RVC][F5] Device for the F5-TTS part.",
    "f5rvc_f5_speed": "[F5+RVC][F5] Speech speed for the F5-TTS part.",
    "f5rvc_f5_nfe_step": "[F5+RVC][F5] Diffusion steps for the F5-TTS part.",
    "f5rvc_f5_remove_silence": "[F5+RVC][F5] Remove silence for the F5-TTS part.",
    "f5rvc_rvc_pitch": "[F5+RVC][RVC] Voice pitch for the RVC part.",
    "f5rvc_index_rate": "[F5+RVC][RVC] Index rate for the RVC part.",
    "f5rvc_protect": "[F5+RVC][RVC] Consonant protection for the RVC part.",
    "f5rvc_filter_radius": "[F5+RVC][RVC] F0 filter radius for the RVC part.",
    "f5rvc_rvc_rms_mix_rate": "[F5+RVC][RVC] RMS mixing for the RVC part.",
    "f5rvc_is_half": "[F5+RVC][RVC] Half-precision for the RVC part.",
    "f5rvc_f0method": "[F5+RVC][RVC] F0 method for the RVC part.",
    "f5rvc_use_index_file": "[F5+RVC][RVC] Use the .index file to improve the model's voice timbre matching.",

    "tmp_directory": "Folder for temporary files created during operation (e.g., intermediate audio files).",
    "verbose": "Enable detailed debug information output to the console for diagnosing problems.",
    "cuda_toolkit": "Presence of installed NVIDIA CUDA Toolkit. Required for some functions (e.g., torch.compile) and working with NVIDIA GPUs.",
    "windows_sdk": "Presence of installed Windows SDK. May be required for compiling some Python dependencies.",
}

default_description_text = "Наведите курсор на элемент интерфейса для получения описания."
default_description_text_en = "Hover over an interface element to get a description."

try:
    from utils.gpu_utils import check_gpu_provider, get_cuda_devices, get_gpu_name_by_id
except ImportError:
    logger.info(_("Предупреждение: Модуль GpuUtils не найден. Функции определения GPU не будут работать.", "Warning: GpuUtils module not found. GPU detection functions will not work."))
    def check_gpu_provider(): return None
    def get_cuda_devices(): return []

from PyQt6.QtCore import QObject, QThread, pyqtSignal, QTimer, Qt
class _InstallWorker(QObject):
    progress = pyqtSignal(int)
    status   = pyqtSignal(str)
    log      = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, local_voice, model_id):
        super().__init__()
        self.local_voice = local_voice
        self.model_id    = model_id

    # --------------------------------------------------------
    def run(self):
        self.log.emit("[DEBUG] worker.run() стартовал")
        try:
            ok = self.local_voice.download_model(
                self.model_id,
                progress_cb=self.progress.emit,
                status_cb=self.status.emit,
                log_cb=self.log.emit
            )
        except Exception as e:
            import traceback, io
            buf = io.StringIO()
            traceback.print_exc(file=buf)
            self.log.emit("[EXCEPTION]\n" + buf.getvalue())
            ok = False
        self.finished.emit(ok)

class VoiceCollapsibleSection(QFrame):
    def __init__(self, parent, title, collapsed=False, update_scrollregion_func=None, clear_description_func=None):
        super().__init__(parent)
        
        def _angle_icon(kind: str, size: int = 10):
            """kind: 'right' | 'down'"""
            import qtawesome as qta
            name = "fa6s.angle-right" if kind == "right" else "fa6s.angle-down"
            return qta.icon(name, color="#f0f0f0").pixmap(size, size)

        self.update_scrollregion = update_scrollregion_func
        self.clear_description = clear_description_func or (lambda event=None: None)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 1)
        main_layout.setSpacing(0)
        
        # Header
        self.header_frame = QFrame()
        self.header_frame.setObjectName("VoiceCollapsibleHeader")
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(5, 2, 5, 2)
        
        # ► / ▼  →  иконки
        self.arrow = QLabel()
        self.arrow_pix_right = _angle_icon("right", 10)
        self.arrow_pix_down  = _angle_icon("down",  10)
        self.arrow.setPixmap(self.arrow_pix_right if collapsed else self.arrow_pix_down)
        self.arrow.setFixedWidth(15)
        
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("color: white; font-weight: bold; font-size: 9pt;")
        
        header_layout.addWidget(self.arrow)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        
        # Content frame
        self.content_frame = QFrame()
        self.content_frame.setObjectName("VoiceCollapsibleContent")
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(1, 0, 1, 1)
        self.content_layout.setSpacing(1)
        
        main_layout.addWidget(self.header_frame)
        main_layout.addWidget(self.content_frame)
        
        # Click handlers
        self.header_frame.mousePressEvent = self.toggle
        self.arrow.mousePressEvent = self.toggle
        self.title_label.mousePressEvent = self.toggle
        
        self.is_collapsed = collapsed
        self.row_count = 0
        self.widgets = {}
        
        if self.is_collapsed:
            self.collapse(update_scroll=False)
        else:
            self.expand(update_scroll=False)

    def toggle(self, event=None):
        if self.is_collapsed:
            self.expand()
        else:
            self.collapse()
        self.is_collapsed = not self.is_collapsed
        if self.update_scrollregion:
            QTimer.singleShot(10, self.update_scrollregion)

    def collapse(self, update_scroll=True):
        self.arrow.setPixmap(self.arrow_pix_right)
        self.content_frame.setVisible(False)
        if update_scroll and self.update_scrollregion:
            QTimer.singleShot(10, self.update_scrollregion)

    def expand(self, update_scroll=True):
        self.arrow.setPixmap(self.arrow_pix_down)
        self.content_frame.setVisible(True)
        if update_scroll and self.update_scrollregion:
            QTimer.singleShot(10, self.update_scrollregion)

    def add_row(self, key, label_text, widget_type, options, setting_info, show_setting_description=None):
        row_height = 28
        is_locked = setting_info.get("locked", False)
        
        # Create horizontal layout for the row
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 1, 0, 0)
        
        # Label
        label_container = QFrame()
        label_container.setObjectName("VoiceSettingLabel")
        label_container.setFixedHeight(row_height)
        label_layout = QHBoxLayout(label_container)
        label_layout.setContentsMargins(10, 3, 10, 3)
        
        label = QLabel(label_text)
        label.setStyleSheet(f"color: {'#888888' if is_locked else 'white'}; font-size: 8pt;")
        label_layout.addWidget(label)
        
        # Widget container
        widget_container = QFrame()
        widget_container.setObjectName("VoiceSettingWidget")
        widget_container.setFixedHeight(row_height)
        widget_layout = QHBoxLayout(widget_container)
        widget_layout.setContentsMargins(5, 2, 5, 2)
        
        widget = None
        widget_var = None
        current_value = options.get("default")
        
        if widget_type == "entry":
            widget = QLineEdit()
            widget.setEnabled(not is_locked)
            if current_value is not None:
                widget.setText(str(current_value))
            widget_var = widget
            widget_layout.addWidget(widget)
            
        elif widget_type == "combobox":
            widget = QComboBox()
            values_list = options.get("values", [])
            if not isinstance(values_list, (list, tuple)):
                values_list = []
            
            widget.addItems([str(v) for v in values_list])
            widget.setEnabled(not is_locked)
            
            if current_value is not None and values_list:
                str_value = str(current_value)
                str_values = [str(v) for v in values_list]
                try:
                    index = str_values.index(str_value)
                    widget.setCurrentIndex(index)
                except ValueError:
                    if values_list:
                        widget.setCurrentIndex(0)
            
            widget_var = widget
            widget_layout.addWidget(widget)
            
        elif widget_type == "checkbutton":
            widget = QCheckBox()
            widget.setEnabled(not is_locked)
            
            bool_value = False
            if isinstance(current_value, str):
                bool_value = current_value.lower() == 'true'
            elif current_value is not None:
                bool_value = bool(current_value)
            
            widget.setChecked(bool_value)
            widget_var = widget
            widget_layout.addWidget(widget)
            widget_layout.addStretch()
        
        if widget:
            self.widgets[key] = {'widget': widget, 'variable': widget_var}
            
            if show_setting_description:
                for w in [label_container, label, widget_container, widget]:
                    w.enterEvent = lambda e, k=key: show_setting_description(k)
                    w.leaveEvent = lambda e: self.clear_description()
        
        # Add row to content
        row_layout.addWidget(label_container, 4)
        row_layout.addWidget(widget_container, 5)
        
        self.content_layout.addLayout(row_layout)
        self.row_count += 1
        
        return widget

    def get_values(self):
        values = {}
        for key, data in self.widgets.items():
            widget = data.get('widget')
            value = None
            try:
                if isinstance(widget, QComboBox):
                    value = widget.currentText()
                elif isinstance(widget, QLineEdit):
                    value = widget.text()
                elif isinstance(widget, QCheckBox):
                    value = widget.isChecked()
                values[key] = value
            except Exception as e:
                logger.info(f"{_('Ошибка получения значения для', 'Error getting value for')} {key}: {e}")
                values[key] = None
        return values


class VoiceModelSettingsWindow(QWidget):

    def _on_progress(self, value: int):
        """
        Получает процент (0-100) из воркера.
        Здесь можно обновлять полоску прогресса,
        статус-бар или просто выводить в лог.
        """
        print(f"F5-TTS install progress: {value}%")

    def __init__(self, master=None, config_dir=None, on_save_callback=None, local_voice=None, check_installed_func=None):
        super().__init__(master)
        
        self.setWindowTitle(_("Настройки и Установка Локальных Моделей", "Settings and Installation of Local Models"))
        self.setMinimumSize(750, 500)
        self.resize(875, 800)
        
        # Apply stylesheet
        self.setStyleSheet(get_stylesheet())
        
        self.local_voice = local_voice
        self.check_installed_func = check_installed_func
        self.config_dir = config_dir or os.path.dirname(os.path.abspath(__file__))
        self.settings_values_file = os.path.join(self.config_dir, "voice_model_settings.json")
        self.installed_models_file = os.path.join(self.config_dir, "installed_models.txt")
        self.on_save_callback = on_save_callback

        self.model_descriptions = model_descriptions_en if SettingsManager.get("LANGUAGE") == "EN" else model_descriptions
        self.setting_descriptions = setting_descriptions_en if SettingsManager.get("LANGUAGE") == "EN" else setting_descriptions
        self.default_description_text = default_description_text_en if SettingsManager.get("LANGUAGE") == "EN" else default_description_text

        self.detected_gpu_vendor = check_gpu_provider()
        self.detected_cuda_devices = []
        self.gpu_name = None

        if self.detected_gpu_vendor == "NVIDIA":
            self.detected_cuda_devices = get_cuda_devices()
            if self.detected_cuda_devices:
                try:
                    first_device_id = self.detected_cuda_devices[0]
                    self.gpu_name = get_gpu_name_by_id(first_device_id)
                    if self.gpu_name:
                        logger.info(f"{_('Обнаружена GPU:', 'Detected GPU:')} {self.gpu_name}")
                    else:
                        logger.info(f"{_('Не удалось получить имя для GPU', 'Could not get name for GPU')} {first_device_id}")
                except Exception as e:
                    logger.info(f"{_('Предупреждение: Не удалось получить имя GPU:', 'Warning: Could not get GPU name:')} {e}")

        self.description_label_widget = None
        self.settings_sections = {}
        self.model_action_buttons = {}
        self.installed_models = set()
        self.scrollable_frame_settings = None
        self.placeholder_label_settings = None
        self.top_frame_settings = None
        self.models_canvas = None
        self.settings_canvas = None
        self.models_scrollable_area = None
        self.local_voice_models = []

        self.load_installed_models_state()
        self.load_settings()
        
        self.docs_manager = DocsManager()
        self._check_system_dependencies()
        
        self._initialize_layout()
        self._create_model_panels()
        self.display_installed_models_settings()

        QTimer.singleShot(100, self._update_settings_scrollregion)
        QTimer.singleShot(100, self._update_models_scrollregion)

    def get_default_model_structure(self):
        return [
             {
                "id": "low", "name": "Edge-TTS + RVC", "min_vram": 3, "rec_vram": 4,
                "gpu_vendor": ["NVIDIA", "AMD"], "size_gb": 3,
                "settings": [
                    {"key": "device", "label": _("Устройство RVC", "RVC Device"), "type": "combobox", "options": { "values_nvidia": ["dml", "cuda:0", "cpu"], "default_nvidia": "cuda:0", "values_amd": ["dml", "cpu"], "default_amd": "dml", "values_other": ["cpu", "mps:0"], "default_other": "cpu" }},
                     {"key": "is_half", "label": _("Half-precision RVC", "Half-precision RVC"), "type": "combobox", "options": {"values": ["True", "False"], "default_nvidia": "True", "default_amd": "False", "default_other": "False"}},
                    {"key": "f0method", "label": _("Метод F0 (RVC)", "F0 Method (RVC)"), "type": "combobox", "options": { "values_nvidia": ["pm", "rmvpe", "crepe", "harvest", "fcpe", "dio"], "default_nvidia": "rmvpe", "values_amd": ["rmvpe", "harvest", "pm", "dio"], "default_amd": "pm", "values_other": ["pm", "rmvpe", "crepe", "harvest", "fcpe", "dio"], "default_other": "pm" }},
                    {"key": "pitch", "label": _("Высота голоса RVC (пт)", "RVC Pitch (semitones)"), "type": "entry", "options": {"default": "6"}},
                    {"key": "use_index_file", "label": _("Исп. .index файл (RVC)", "Use .index file (RVC)"), "type": "checkbutton", "options": {"default": True}},
                    {"key": "index_rate", "label": _("Соотношение индекса RVC", "RVC Index Rate"), "type": "entry", "options": {"default": "0.75"}},
                    {"key": "protect", "label": _("Защита согласных (RVC)", "Consonant Protection (RVC)"), "type": "entry", "options": {"default": "0.33"}},
                    {"key": "tts_rate", "label": _("Скорость TTS (%)", "TTS Speed (%)"), "type": "entry", "options": {"default": "0"}},
                    {"key": "filter_radius", "label": _("Радиус фильтра F0 (RVC)", "F0 Filter Radius (RVC)"), "type": "entry", "options": {"default": "3"}},
                    {"key": "rms_mix_rate", "label": _("Смешивание RMS (RVC)", "RMS Mixing (RVC)"), "type": "entry", "options": {"default": "0.5"}},
                ]
            },
            {
                "id": "low+", "name": "Silero + RVC", "min_vram": 3, "rec_vram": 4,
                "gpu_vendor": ["NVIDIA", "AMD"], "size_gb": 3,
                "settings": [
                    {"key": "silero_rvc_device", "label": _("Устройство RVC", "RVC Device"), "type": "combobox", "options": { "values_nvidia": ["dml", "cuda:0", "cpu"], "default_nvidia": "cuda:0", "values_amd": ["dml", "cpu"], "default_amd": "dml", "values_other": ["cpu", "dml"], "default_other": "cpu" }},
                    {"key": "silero_rvc_is_half", "label": _("Half-precision RVC", "Half-precision RVC"), "type": "combobox", "options": {"values": ["True", "False"], "default_nvidia": "True", "default_amd": "False", "default_other": "False"}},
                    {"key": "silero_rvc_f0method", "label": _("Метод F0 (RVC)", "F0 Method (RVC)"), "type": "combobox", "options": { "values_nvidia": ["pm", "rmvpe", "crepe", "harvest", "fcpe", "dio"], "default_nvidia": "rmvpe", "values_amd": ["rmvpe", "harvest", "pm", "dio"], "default_amd": "pm", "values_other": ["pm", "rmvpe", "harvest", "dio"], "default_other": "pm" }},
                    {"key": "silero_rvc_pitch", "label": _("Высота голоса RVC (пт)", "RVC Pitch (semitones)"), "type": "entry", "options": {"default": "6"}},
                    {"key": "silero_rvc_use_index_file", "label": _("Исп. .index файл (RVC)", "Use .index file (RVC)"), "type": "checkbutton", "options": {"default": True}},
                    {"key": "silero_rvc_index_rate", "label": _("Соотношение индекса RVC", "RVC Index Rate"), "type": "entry", "options": {"default": "0.75"}},
                    {"key": "silero_rvc_protect", "label": _("Защита согласных (RVC)", "Consonant Protection (RVC)"), "type": "entry", "options": {"default": "0.33"}},
                    {"key": "silero_rvc_filter_radius", "label": _("Радиус фильтра F0 (RVC)", "F0 Filter Radius (RVC)"), "type": "entry", "options": {"default": "3"}},
                    {"key": "silero_rvc_rms_mix_rate", "label": _("Смешивание RMS (RVC)", "RMS Mixing (RVC)"), "type": "entry", "options": {"default": "0.5"}},
                    
                    {"key": "silero_device", "label": _("Устройство Silero", "Silero Device"), "type": "combobox", "options": {"values_nvidia": ["cuda", "cpu"], "default_nvidia": "cuda", "values_amd": ["cpu"], "default_amd": "cpu", "values_other": ["cpu"], "default_other": "cpu"}},
                    {"key": "silero_sample_rate", "label": _("Частота Silero", "Silero Sample Rate"), "type": "combobox", "options": {"values": ["48000", "24000", "16000"], "default": "48000"}},
                    {"key": "silero_put_accent", "label": _("Акценты Silero", "Silero Accents"), "type": "checkbutton", "options": {"default": True}},
                    {"key": "silero_put_yo", "label": _("Буква Ё Silero", "Silero Letter Yo"), "type": "checkbutton", "options": {"default": True}}
                ]
            },
            {
                "id": "medium", "name": "Fish Speech", "min_vram": 3, "rec_vram": 6, "gpu_vendor": ["NVIDIA"], "size_gb": 5,
                 "settings": [
                    {"key": "device", "label": _("Устройство", "Device"), "type": "combobox", "options": {"values": ["cuda", "cpu", "mps"], "default": "cuda"}},
                    {"key": "half", "label": _("Half-precision", "Half-precision"), "type": "combobox", "options": {"values": ["False", "True"], "default": "False"}},
                    {"key": "temperature", "label": _("Температура", "Temperature"), "type": "entry", "options": {"default": "0.7"}},
                    {"key": "top_p", "label": _("Top-P", "Top-P"), "type": "entry", "options": {"default": "0.7"}},
                    {"key": "repetition_penalty", "label": _("Штраф повторений", "Repetition Penalty"), "type": "entry", "options": {"default": "1.2"}},
                    {"key": "chunk_length", "label": _("Размер чанка (~символов)", "Chunk Size (~chars)"), "type": "entry", "options": {"default": "200"}},
                    {"key": "max_new_tokens", "label": _("Макс. токены", "Max Tokens"), "type": "entry", "options": {"default": "1024"}},
                    {"key": "compile_model", "label": _("Компиляция модели", "Compile Model"), "type": "combobox", "options": {"values": ["False", "True"], "default": "False"}, "locked": True},
                    {"key": "seed", "label": _("Seed", "Seed"), "type": "entry", "options": {"default": "0"}},
                ]
            },
            {
                "id": "medium+", "name": "Fish Speech+", "min_vram": 3, "rec_vram": 6, "gpu_vendor": ["NVIDIA"], "size_gb": 10,
                "rtx30plus": True,
                 "settings": [
                    {"key": "device", "label": _("Устройство", "Device"), "type": "combobox", "options": {"values": ["cuda", "cpu", "mps"], "default": "cuda"}},
                    {"key": "half", "label": _("Half-precision", "Half-precision"), "type": "combobox", "options": {"values": ["True", "False"], "default": "False"}, "locked": True},
                    {"key": "temperature", "label": _("Температура", "Temperature"), "type": "entry", "options": {"default": "0.7"}},
                    {"key": "top_p", "label": _("Top-P", "Top-P"), "type": "entry", "options": {"default": "0.8"}},
                    {"key": "repetition_penalty", "label": _("Штраф повторений", "Repetition Penalty"), "type": "entry", "options": {"default": "1.1"}},
                    {"key": "chunk_length", "label": _("Размер чанка (~символов)", "Chunk Size (~chars)"), "type": "entry", "options": {"default": "200"}},
                    {"key": "max_new_tokens", "label": _("Макс. токены", "Max Tokens"), "type": "entry", "options": {"default": "1024"}},
                    {"key": "compile_model", "label": _("Компиляция модели", "Compile Model"), "type": "combobox", "options": {"values": ["False", "True"], "default": "True"}, "locked": True},
                    {"key": "seed", "label": _("Seed", "Seed"), "type": "entry", "options": {"default": "0"}},
                 ]
            },
            {
                "id": "medium+low", "name": "Fish Speech+ + RVC", "min_vram": 5, "rec_vram": 8, "gpu_vendor": ["NVIDIA"], "size_gb": 15,
                "rtx30plus": True,
                "settings": [
                    {"key": "fsprvc_fsp_device", "label": _("[FSP] Устройство", "[FSP] Device"), "type": "combobox", "options": {"values": ["cuda", "cpu", "mps"], "default": "cuda"}},
                    {"key": "fsprvc_fsp_half", "label": _("[FSP] Half-precision", "[FSP] Half-precision"), "type": "combobox", "options": {"values": ["True", "False"], "default": "False"}, "locked": True},
                    {"key": "fsprvc_fsp_temperature", "label": _("[FSP] Температура", "[FSP] Temperature"), "type": "entry", "options": {"default": "0.7"}},
                    {"key": "fsprvc_fsp_top_p", "label": _("[FSP] Top-P", "[FSP] Top-P"), "type": "entry", "options": {"default": "0.7"}},
                    {"key": "fsprvc_fsp_repetition_penalty", "label": _("[FSP] Штраф повторений", "[FSP] Repetition Penalty"), "type": "entry", "options": {"default": "1.2"}},
                    {"key": "fsprvc_fsp_chunk_length", "label": _("[FSP] Размер чанка (слов)", "[FSP] Chunk Size (words)"), "type": "entry", "options": {"default": "200"}},
                    {"key": "fsprvc_fsp_max_tokens", "label": _("[FSP] Макс. токены", "[FSP] Max Tokens"), "type": "entry", "options": {"default": "1024"}},
                    {"key": "fsprvc_fsp_seed", "label": _("[FSP] Seed", "[FSP] Seed"), "type": "entry", "options": {"default": "0"}},
                    {"key": "fsprvc_rvc_device", "label": _("[RVC] Устройство", "[RVC] Device"), "type": "combobox", "options": {"values": ["cuda:0", "cpu", "mps:0", "dml"], "default_nvidia": "cuda:0", "default_amd": "dml"}},
                    {"key": "fsprvc_is_half", "label": _("[RVC] Half-precision", "[RVC] Half-precision"), "type": "combobox", "options": {"values": ["True", "False"], "default_nvidia": "True", "default_amd": "False"}},
                    {"key": "fsprvc_f0method", "label": _("[RVC] Метод F0", "[RVC] F0 Method"), "type": "combobox", "options": {"values": ["pm", "rmvpe", "crepe", "harvest", "fcpe", "dio"], "default_nvidia": "rmvpe", "default_amd": "dio"}},
                    {"key": "fsprvc_rvc_pitch", "label": _("[RVC] Высота голоса (пт)", "[RVC] Pitch (semitones)"), "type": "entry", "options": {"default": "0"}},
                    {"key": "fsprvc_use_index_file", "label": _("[RVC] Исп. .index файл", "[RVC] Use .index file"), "type": "checkbutton", "options": {"default": True}},
                    {"key": "fsprvc_index_rate", "label": _("[RVC] Соотн. индекса", "[RVC] Index Rate"), "type": "entry", "options": {"default": "0.75"}},
                    {"key": "fsprvc_protect", "label": _("[RVC] Защита согласных", "[RVC] Consonant Protection"), "type": "entry", "options": {"default": "0.33"}},
                    {"key": "fsprvc_filter_radius", "label": _("[RVC] Радиус фильтра F0", "[RVC] F0 Filter Radius"), "type": "entry", "options": {"default": "3"}},
                    {"key": "fsprvc_rvc_rms_mix_rate", "label": _("[RVC] Смешивание RMS", "[RVC] RMS Mixing"), "type": "entry", "options": {"default": "0.5"}},
                ]
            },
            {
                "id": "high",
                "name": "F5-TTS",
                "min_vram": 4,
                "rec_vram": 8,
                "gpu_vendor": ["NVIDIA"],
                "size_gb": 4,
                "settings": [
                    {"key": "speed", "label": _("Скорость речи", "Speech Speed"), "type": "entry", "options": {"default": "1.0"}},
                    {"key": "nfe_step", "label": _("Шаги диффузии", "Diffusion Steps"), "type": "entry", "options": {"default": "32"}},
                    {"key": "remove_silence", "label": _("Удалять тишину", "Remove Silence"), "type": "checkbutton", "options": {"default": True}},
                    {"key": "seed", "label": _("Seed", "Seed"), "type": "entry", "options": {"default": "0"}}
                ]
            },
            {
                "id": "high+low",
                "name": "F5-TTS + RVC",
                "min_vram": 6,
                "rec_vram": 8,
                "gpu_vendor": ["NVIDIA"],
                "size_gb": 7,
                "settings": [
                    {"key": "f5rvc_f5_device", "label": _("[F5] Устройство", "[F5] Device"), "type": "combobox", "options": {"values": ["cuda", "cpu"], "default": "cuda"}},
                    {"key": "f5rvc_f5_speed", "label": _("[F5] Скорость речи", "[F5] Speech Speed"), "type": "entry", "options": {"default": "1.0"}},
                    {"key": "f5rvc_f5_nfe_step", "label": _("[F5] Шаги диффузии", "[F5] Diffusion Steps"), "type": "entry", "options": {"default": "32"}},
                    {"key": "f5rvc_f5_seed", "label": _("[F5] Seed", "[F5] Seed"), "type": "entry", "options": {"default": "0"}},
                    {"key": "f5rvc_f5_remove_silence", "label": _("[F5] Удалять тишину", "[F5] Remove Silence"), "type": "checkbutton", "options": {"default": True}},
                    {"key": "f5rvc_rvc_pitch", "label": _("[RVC] Высота голоса (пт)", "[RVC] Pitch (semitones)"), "type": "entry", "options": {"default": "0"}},
                    {"key": "f5rvc_index_rate", "label": _("[RVC] Соотн. индекса", "[RVC] Index Rate"), "type": "entry", "options": {"default": "0.75"}},
                    {"key": "f5rvc_protect", "label": _("[RVC] Защита согласных", "[RVC] Consonant Protection"), "type": "entry", "options": {"default": "0.33"}},
                    {"key": "f5rvc_filter_radius", "label": _("[RVC] Радиус фильтра F0", "[RVC] F0 Filter Radius"), "type": "entry", "options": {"default": "3"}},
                    {"key": "f5rvc_rvc_rms_mix_rate", "label": _("[RVC] Смешивание RMS", "[RVC] RMS Mixing"), "type": "entry", "options": {"default": "0.5"}},
                    {"key": "f5rvc_is_half", "label": _("[RVC] Half-precision", "[RVC] Half-precision"), "type": "combobox", "options": {"values": ["True", "False"], "default": "True"}},
                    {"key": "f5rvc_f0method", "label": _("[RVC] Метод F0", "[RVC] F0 Method"), "type": "combobox", "options": {"values": ["pm", "rmvpe", "crepe", "harvest", "fcpe", "dio"], "default": "rmvpe"}},
                    {"key": "f5rvc_use_index_file", "label": _("[RVC] Исп. .index файл", "[RVC] Use .index file"), "type": "checkbutton", "options": {"default": True}},
                ]
            }
        ]

    def load_settings(self):
        default_model_structure = self.get_default_model_structure()
        adapted_default_structure = self.finalize_model_settings(
            default_model_structure, self.detected_gpu_vendor, self.detected_cuda_devices
        )
        saved_values = {}
        try:
            if os.path.exists(self.settings_values_file):
                with open(self.settings_values_file, "r", encoding="utf-8") as f:
                    saved_values = json.load(f)
        except Exception as e:
            logger.info(f"{_('Ошибка загрузки сохраненных значений из', 'Error loading saved values from')} {self.settings_values_file}: {e}")
            saved_values = {}
        merged_model_structure = copy.deepcopy(adapted_default_structure)
        for model_data in merged_model_structure:
            model_id = model_data.get("id")
            if model_id in saved_values:
                model_saved_values = saved_values[model_id]
                if isinstance(model_saved_values, dict):
                    for setting in model_data.get("settings", []):
                        setting_key = setting.get("key")
                        if setting_key in model_saved_values:
                            setting.setdefault("options", {})["default"] = model_saved_values[setting_key]
        self.local_voice_models = merged_model_structure
        logger.info(_("Загрузка и адаптация настроек завершена.", "Loading and adaptation of settings completed."))

    def load_installed_models_state(self):
        """Загружает список установленных моделей из файла."""
        self.installed_models = set()
        if not self.local_voice or not self.check_installed_func:
            try:
                if os.path.exists(self.installed_models_file):
                    with open(self.installed_models_file, "r", encoding="utf-8") as f:
                        self.installed_models.update(line.strip() for line in f if line.strip())
                    logger.info(f"{_('Загружен список установленных моделей из файла:', 'Loaded list of installed models from file:')} {self.installed_models}") 
            except Exception as e:
                logger.info(f"{_('Ошибка загрузки состояния из', 'Error loading state from')} {self.installed_models_file}: {e}")
        else:
            logger.info(_("Проверка установленных моделей через check_installed_func...", "Checking installed models via check_installed_func..."))
            for model_data in self.get_default_model_structure():
                model_id = model_data.get("id")
                if model_id:
                    is_installed = False
                    if model_id == "low": is_installed = self.check_installed_func("tts_with_rvc")
                    elif model_id == "low+": is_installed = self.check_installed_func("tts_with_rvc")
                    elif model_id == "medium": is_installed = self.check_installed_func("fish_speech_lib")
                    elif model_id == "medium+": is_installed = self.check_installed_func("fish_speech_lib") and self.check_installed_func("triton")
                    elif model_id == "medium+low": is_installed = self.check_installed_func("tts_with_rvc") and self.check_installed_func("fish_speech_lib") and self.check_installed_func("triton")
                    elif model_id == "high": is_installed = self.check_installed_func("f5_tts")
                    elif model_id == "high+low": is_installed = self.check_installed_func("f5_tts") and self.check_installed_func("tts_with_rvc")

                    if is_installed:
                        self.installed_models.add(model_id)
            logger.info(f"{_('Актуальный список установленных моделей:', 'Current list of installed models:')} {self.installed_models}")

    def save_settings(self):
        settings_to_save = {}
        for model_id, section in self.settings_sections.items():
            if model_id in self.installed_models and section:
                try:
                    settings_to_save[model_id] = section.get_values()
                except Exception as e:
                    logger.info(f"{_('Ошибка при сборе значений из UI для модели', 'Error collecting UI values for model')} '{model_id}': {e}")
        if settings_to_save:
            try:
                with open(self.settings_values_file, "w", encoding="utf-8") as f:
                    json.dump(settings_to_save, f, indent=4, ensure_ascii=False)
            except Exception as e:
                logger.info(f"{_('Ошибка сохранения значений настроек в', 'Error saving settings values to')} {self.settings_values_file}: {e}")
        if self.on_save_callback:
            callback_data = {
                 "installed_models": list(self.installed_models),
                 "models_data": self.local_voice_models
            }
            self.on_save_callback(callback_data)

    def finalize_model_settings(self, models_list, detected_vendor, cuda_devices):
        final_models = copy.deepcopy(models_list)

        gpu_name_upper = self.gpu_name.upper() if self.gpu_name else ""
        force_fp32 = False
        if detected_vendor == "NVIDIA" and gpu_name_upper:
            if (
                ("16" in gpu_name_upper and "V100" not in gpu_name_upper)
                or "P40" in gpu_name_upper
                or "P10" in gpu_name_upper
                or "1060" in gpu_name_upper
                or "1070" in gpu_name_upper
                or "1080" in gpu_name_upper
            ):
                logger.info(f"{_('Обнаружена GPU', 'Detected GPU')} {self.gpu_name}, {_('принудительно используется FP32 для совместимых настроек.', 'forcing FP32 for compatible settings.')}")
                force_fp32 = True
        elif detected_vendor == "AMD":
            force_fp32 = True

        for model in final_models:
            model_vendors = model.get("gpu_vendor", [])
            vendor_to_adapt_for = None
            if detected_vendor == "NVIDIA" and "NVIDIA" in model_vendors: vendor_to_adapt_for = "NVIDIA"
            elif detected_vendor == "AMD" and "AMD" in model_vendors: vendor_to_adapt_for = "AMD"
            elif not detected_vendor or detected_vendor not in model_vendors: vendor_to_adapt_for = "OTHER"
            elif detected_vendor in model_vendors: vendor_to_adapt_for = detected_vendor

            for setting in model.get("settings", []):
                options = setting.get("options", {})
                setting_key = setting.get("key")
                widget_type = setting.get("type")
                is_device_setting = "device" in str(setting_key).lower()
                is_half_setting = setting_key in ["is_half", "fsprvc_is_half", "half", "fsprvc_fsp_half"]

                final_values_list = None
                adapt_key_suffix = ""
                if vendor_to_adapt_for == "NVIDIA": adapt_key_suffix = "_nvidia"
                elif vendor_to_adapt_for == "AMD": adapt_key_suffix = "_amd"
                elif vendor_to_adapt_for == "OTHER": adapt_key_suffix = "_other"

                values_key = f"values{adapt_key_suffix}"
                default_key = f"default{adapt_key_suffix}"

                if values_key in options: final_values_list = options[values_key]
                elif "values" in options: final_values_list = options["values"]

                if default_key in options: options["default"] = options[default_key]

                if vendor_to_adapt_for == "NVIDIA" and is_device_setting:
                    base_nvidia_values = options.get("values_nvidia", [])
                    base_other_values = options.get("values_other", ["cpu"])
                    base_non_cuda_provider = base_nvidia_values if base_nvidia_values else base_other_values
                    non_cuda_options = [v for v in base_non_cuda_provider if not str(v).startswith("cuda")]
                    if cuda_devices: final_values_list = cuda_devices + non_cuda_options
                    else: final_values_list = [v for v in base_other_values if v in ["cpu", "mps"]] or ["cpu"]

                if final_values_list is not None and widget_type == "combobox":
                    options["values"] = final_values_list

                keys_to_remove = [k for k in options if k.startswith("values_") or k.startswith("default_")]
                for key_to_remove in keys_to_remove: options.pop(key_to_remove, None)

                if force_fp32 and is_half_setting:
                    options["default"] = "False"
                    setting["locked"] = True
                    logger.info(f"  - {_('Принудительно', 'Forcing')} '{setting_key}' = False {_('и заблокировано.', 'and locked.')}")
                elif is_half_setting:
                    logger.info(f"  - '{setting_key}' = True - Доступен.")

                if widget_type == "combobox" and "default" in options and "values" in options:
                    current_values = options["values"]
                    if isinstance(current_values, list):
                        current_default = options["default"]
                        str_values = [str(v) for v in current_values]
                        str_default = str(current_default)
                        if str_default not in str_values:
                            options["default"] = str_values[0] if str_values else ""
                    else:
                         options["default"] = ""
        return final_models

    def get_model_parameters(self, model_id):
        parameters = {}
        settings_file = self.settings_values_file
        if not os.path.exists(settings_file): return parameters
        try:
            with open(settings_file, "r", encoding="utf-8") as f:
                all_saved_data = json.load(f)
            if isinstance(all_saved_data, dict):
                parameters = all_saved_data.get(model_id, {})
        except Exception as e:
            logger.info(f"{_('Ошибка чтения файла настроек', 'Error reading settings file')} {settings_file}: {e}")
        return parameters

    def _initialize_layout(self):
        # Главный layout устанавливаем сразу на self
        main_widget_layout = QVBoxLayout(self)
        main_widget_layout.setContentsMargins(0, 0, 0, 0)
        
        # Создаем контейнер для основного содержимого
        content_widget = QWidget()
        main_layout = QHBoxLayout(content_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Left panel
        left_panel = QWidget()
        left_panel.setFixedWidth(280)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)
        
        # Description frame
        description_frame = QFrame()
        description_frame.setObjectName("DescriptionFrame")
        description_frame.setFixedHeight(135)
        desc_layout = QVBoxLayout(description_frame)
        desc_layout.setContentsMargins(10, 5, 10, 10)
        
        desc_title = QLabel(_("Описание:", "Description"))
        desc_title.setStyleSheet("font-weight: bold; font-size: 9pt;")
        desc_layout.addWidget(desc_title)
        
        self.description_label_widget = QLabel(self.default_description_text)
        self.description_label_widget.setWordWrap(True)
        self.description_label_widget.setStyleSheet("color: #cccccc; font-size: 9pt;")
        self.description_label_widget.setAlignment(Qt.AlignmentFlag.AlignTop)
        desc_layout.addWidget(self.description_label_widget)
        desc_layout.addStretch()
        
        left_layout.addWidget(description_frame)
        
        # Models list
        models_title = QLabel(_("Доступные Модели:", "Available models"))
        models_title.setStyleSheet("font-weight: bold; font-size: 10pt;")
        left_layout.addWidget(models_title)
        
        # Models scroll area
        self.models_canvas = QScrollArea()
        self.models_canvas.setWidgetResizable(True)
        self.models_canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.models_scrollable_area = QWidget()
        self.models_layout = QVBoxLayout(self.models_scrollable_area)
        self.models_layout.setContentsMargins(0, 0, 0, 0)
        self.models_layout.setSpacing(4)
        
        self.models_canvas.setWidget(self.models_scrollable_area)
        left_layout.addWidget(self.models_canvas)
        
        main_layout.addWidget(left_panel)
        
        # Right panel
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Settings scroll area
        self.settings_canvas = QScrollArea()
        self.settings_canvas.setWidgetResizable(True)
        self.settings_canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scrollable_frame_settings = QWidget()
        self.settings_layout = QVBoxLayout(self.scrollable_frame_settings)
        self.settings_layout.setContentsMargins(10, 10, 10, 10)
        
        # Top frame for dependencies status
        self.top_frame_settings = QFrame()
        top_layout = QVBoxLayout(self.top_frame_settings)
        top_layout.setContentsMargins(0, 0, 0, 5)
        
        self._check_and_display_dependencies_status(top_layout)
        
        self.settings_layout.addWidget(self.top_frame_settings)
        
        self.settings_canvas.setWidget(self.scrollable_frame_settings)
        right_layout.addWidget(self.settings_canvas)
        
        main_layout.addWidget(right_panel, 1)
        
        # Bottom buttons
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(10, 10, 10, 10)
        
        close_button = QPushButton(_("Закрыть", "Close"))
        close_button.clicked.connect(self.save_and_quit)
        
        save_button = QPushButton(_("Сохранить", "Save"))
        save_button.clicked.connect(self.save_and_continue)
        save_button.setObjectName("PrimaryButton")
        
        bottom_layout.addStretch()
        bottom_layout.addWidget(close_button)
        bottom_layout.addWidget(save_button)
        
        # Добавляем виджеты в главный layout
        main_widget_layout.addWidget(content_widget, 1)
        main_widget_layout.addWidget(bottom_widget)

    def _check_and_display_dependencies_status(self, layout):
        """Check and display system dependencies status"""
        if platform.system() == "Windows":
            if self.triton_installed and self.triton_checks_performed:
                status_layout = QHBoxLayout()
                
                items = [
                    ("CUDA Toolkit:", self.cuda_found),
                    ("Windows SDK:", self.winsdk_found),
                    ("MSVC:", self.msvc_found)
                ]
                
                for text, found in items:
                    item_layout = QHBoxLayout()
                    item_layout.setSpacing(3)
                    
                    label = QLabel(text)
                    label.setStyleSheet("font-size: 9pt;")
                    item_layout.addWidget(label)
                    
                    status_text = _("Найден", "Found") if found else _("Не найден", "Not Found")
                    status_color = "lightgreen" if found else "#FF6A6A"
                    status_label = QLabel(status_text)
                    status_label.setStyleSheet(f"font-size: 9pt; color: {status_color};")
                    item_layout.addWidget(status_label)
                    
                    status_layout.addLayout(item_layout)
                    status_layout.addSpacing(15)
                
                status_layout.addStretch()
                layout.addLayout(status_layout)
                
                if not (self.cuda_found and self.winsdk_found and self.msvc_found):
                    warning_layout = QHBoxLayout()
                    warning_text = _("⚠️ Для моделей Fish Speech+ / +RVC могут потребоваться все компоненты.", 
                                   "⚠️ Fish Speech+ / +RVC models may require all components.")
                    warning_label = QLabel(warning_text)
                    warning_label.setStyleSheet("color: orange; font-weight: bold; font-size: 9pt;")
                    warning_layout.addWidget(warning_label)
                    
                    doc_link = QLabel(_("[Документация]", "[Documentation]"))
                    doc_link.setStyleSheet("color: #81d4fa; font-weight: bold; font-size: 9pt; text-decoration: underline;")
                    doc_link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                    doc_link.mousePressEvent = lambda e: self.docs_manager.open_doc("installation_guide.html")
                    warning_layout.addWidget(doc_link)
                    
                    warning_layout.addStretch()
                    layout.addLayout(warning_layout)
            
            elif not self.triton_installed:
                warning_label = QLabel(_("Triton не установлен (необходим для Fish Speech+ / +RVC).", 
                                       "Triton not installed (required for Fish Speech+ / +RVC)."))
                warning_label.setStyleSheet("color: orange; font-size: 9pt;")
                layout.addWidget(warning_label)
        else:
            info_label = QLabel(_("Проверка зависимостей Triton доступна только в Windows.", 
                                "Triton dependency check is only available on Windows."))
            info_label.setStyleSheet("color: #aaaaaa; font-size: 9pt;")
            layout.addWidget(info_label)

    def _create_model_panels(self):
        if not self.models_scrollable_area:
            return
            
        # Clear existing panels
        while self.models_layout.count():
            item = self.models_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
                
        self.download_buttons = {}
        
        for model_info in self.local_voice_models:
            panel = self.create_model_panel(self.models_scrollable_area, model_info)
            self.models_layout.addWidget(panel)
            
        self.models_layout.addStretch()
        QTimer.singleShot(50, self._update_models_scrollregion)


    def _clear_settings_layout(self):
        while self.settings_layout.count():
            item = self.settings_layout.takeAt(0) 
            w = item.widget()
            if w:
                w.deleteLater()

    def display_installed_models_settings(self):
        """Display settings for installed models"""
        if not self.scrollable_frame_settings:
            return
            
        # Clear existing settings (except top frame)
        self._clear_settings_layout()
                
        self.settings_sections.clear()
        
        # Re-add top frame first
        self.top_frame_settings = QFrame()
        top_layout = QVBoxLayout(self.top_frame_settings)
        top_layout.setContentsMargins(0, 0, 0, 5)
        self._check_and_display_dependencies_status(top_layout)
        self.settings_layout.addWidget(self.top_frame_settings)
        
        if not self.installed_models:
            self.placeholder_label_settings = QLabel(
                _("Модели не установлены.\n\nНажмите 'Установить' слева для установки модели,\nее настройки появятся здесь.", 
                  "Models not installed.\n\nClick 'Install' on the left to install a model,\nits settings will appear here.")
            )
            self.placeholder_label_settings.setStyleSheet("color: #aaa; font-size: 10pt;")
            self.placeholder_label_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.placeholder_label_settings.setWordWrap(True)
            self.settings_layout.addWidget(self.placeholder_label_settings)
            self.settings_layout.addStretch()
        else:
            any_settings_shown = False
            
            for model_data in self.local_voice_models:
                model_id = model_data.get("id")
                if not model_id or model_id not in self.installed_models:
                    continue
                    
                any_settings_shown = True
                model_name = model_data.get('name', model_id)
                
                section_title = f"{_('Настройки:', 'Settings:')} {model_name}"
                start_collapsed = len(self.installed_models) > 2
                section = VoiceCollapsibleSection(
                    self.scrollable_frame_settings,
                    section_title,
                    collapsed=start_collapsed,
                    update_scrollregion_func=self._update_settings_scrollregion,
                    clear_description_func=self.clear_description
                )
                self.settings_sections[model_id] = section
                
                model_settings = model_data.get("settings", [])
                if model_settings:
                    for setting_info in model_settings:
                        key = setting_info.get("key")
                        label = setting_info.get("label", key)
                        widget_type = setting_info.get("type")
                        options = setting_info.get("options", {})
                        if key and widget_type:
                            section.add_row(
                                key, label, widget_type, options, setting_info,
                                show_setting_description=self.show_setting_description
                            )
                else:
                    no_settings_label = QLabel(_("Специфические настройки отсутствуют.", "Specific settings are missing."))
                    no_settings_label.setStyleSheet("color: #ccc; font-size: 9pt;")
                    section.content_layout.addWidget(no_settings_label)
                    
                self.settings_layout.addWidget(section)
                
            if not any_settings_shown:
                self.placeholder_label_settings = QLabel(
                    _("Не удалось отобразить настройки для установленных моделей.", 
                      "Could not display settings for installed models.")
                )
                self.placeholder_label_settings.setStyleSheet("color: #aaa; font-size: 10pt;")
                self.placeholder_label_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.settings_layout.addWidget(self.placeholder_label_settings)
                
            self.settings_layout.addStretch()
            
        QTimer.singleShot(50, self._update_settings_scrollregion)

    def _check_system_dependencies(self):
        """Check system dependencies"""
        self.cuda_found = False
        self.winsdk_found = False
        self.msvc_found = False
        self.triton_installed = False
        self.triton_checks_performed = False

        if platform.system() != "Windows":
            logger.info(_("Проверка зависимостей Triton актуальна только для Windows.", "Triton dependency check is relevant only for Windows."))
            return

        try:
            from triton.windows_utils import find_cuda, find_winsdk, find_msvc
            self.triton_installed = True

            cuda_result = find_cuda()
            logger.info(f"CUDA find_cuda() result: {cuda_result}")
            if isinstance(cuda_result, (tuple, list)) and len(cuda_result) >= 1:
                cuda_path = cuda_result[0]
                self.cuda_found = cuda_path is not None and os.path.exists(str(cuda_path)) 
            else:
                self.cuda_found = False
            logger.info(f"CUDA Check: Found={self.cuda_found}")

            winsdk_result = find_winsdk(False)
            logger.info(f"WinSDK find_winsdk() result: {winsdk_result}") 
            if isinstance(winsdk_result, (tuple, list)) and len(winsdk_result) >= 1:
                winsdk_paths = winsdk_result[0]
                self.winsdk_found = isinstance(winsdk_paths, list) and bool(winsdk_paths)
            else:
                self.winsdk_found = False
            logger.info(f"WinSDK Check: Found={self.winsdk_found}")

            msvc_result = find_msvc(False)
            logger.info(f"MSVC find_msvc() result: {msvc_result}")
            if isinstance(msvc_result, (tuple, list)) and len(msvc_result) >= 1:
                msvc_paths = msvc_result[0]
                self.msvc_found = isinstance(msvc_paths, list) and bool(msvc_paths)
            else:
                self.msvc_found = False
            logger.info(f"MSVC Check: Found={self.msvc_found}")

            self.triton_checks_performed = True

        except ImportError:
            logger.info(_("Triton не установлен. Невозможно проверить зависимости CUDA/WinSDK/MSVC.", "Triton not installed. Cannot check CUDA/WinSDK/MSVC dependencies."))
            self.triton_installed = False
        except Exception as e:
            logger.info(f"{_('Ошибка при проверке зависимостей Triton:', 'Error checking Triton dependencies:')} {e}")

    def create_model_panel(self, parent, model_data):
        model_id = model_data["id"]
        model_name = model_data["name"]
        supported_vendors = model_data.get('gpu_vendor', [])
        requires_rtx30plus = model_data.get("rtx30plus", False)
        
        panel = QFrame()
        panel.setObjectName("ModelPanel")
        panel.enterEvent = lambda e: self.show_model_description(model_id)
        panel.leaveEvent = lambda e: self.clear_description()
        
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 5, 10, 6)
        panel_layout.setSpacing(2)
        
        # Title row
        title_layout = QHBoxLayout()
        title_label = QLabel(model_name)
        title_label.setStyleSheet("font-weight: bold; font-size: 10pt;")
        title_label.enterEvent = lambda e: self.show_model_description(model_id)
        title_label.leaveEvent = lambda e: self.clear_description()
        title_layout.addWidget(title_label)
        
        # Warning icon for medium model
        if model_id == "medium":
            warning_icon = QLabel("⚠️")
            warning_icon.setStyleSheet("color: orange; font-size: 9pt;")
            warning_icon.setCursor(QCursor(Qt.CursorShape.WhatsThisCursor))
            medium_tooltip_text = _(
                "Модель 'Fish Speech' не рекомендуется для большинства пользователей.\n\n"
                "Для стабильной скорости генерации требуется мощная видеокарта, "
                "минимальные \"играбельные\" GPU: GeForce RTX 2080 Ti / RTX 2070 Super / GTX 1080 Ti и подобные, "
                "использование на более слабых GPU может привести к очень медленной работе.\n\n"
                "Владельцам RTX30+ рекомендуется использовать модели \"Fish Speech+\", "
                "остальным рекомендуется использовать модель \"Silero + RVC\"",
                "The 'Fish Speech' model is not recommended for most users.\n\n"
                "A powerful graphics card is required for stable generation speed, "
                "minimum \"playable\" GPUs: GeForce RTX 2080 Ti / RTX 2070 Super / GTX 1080 Ti and similar, "
                "using it on weaker GPUs can lead to very slow performance.\n\n"
                "RTX30+ owners are recommended to use \"Fish Speech+\" models, "
                "others are recommended to use the \"Silero + RVC\" model"
            )
            warning_icon.setToolTip(medium_tooltip_text)
            title_layout.addWidget(warning_icon)
        
        # RTX 30+ indicator
        if requires_rtx30plus:
            gpu_meets_requirement = self.is_gpu_rtx30_or_40()
            icon_color = "lightgreen" if gpu_meets_requirement else "orange"
            rtx_label = QLabel("RTX 30+")
            rtx_label.setStyleSheet(f"color: {icon_color}; font-size: 7pt; font-weight: bold;")
            rtx_tooltip_text = _("Требуется GPU NVIDIA RTX 30xx/40xx для оптимальной производительности.", 
                               "Requires NVIDIA RTX 30xx/40xx GPU for optimal performance.") if not gpu_meets_requirement else _("Ваша GPU подходит для этой модели.", "Your GPU is suitable for this model.")
            rtx_label.setToolTip(rtx_tooltip_text)
            title_layout.addWidget(rtx_label)
        
        title_layout.addStretch()
        panel_layout.addLayout(title_layout)
        
        # Info row
        vram_text = f"VRAM: {model_data.get('min_vram', '?')}GB - {model_data.get('rec_vram', '?')}GB"
        gpu_req_text = f"GPU: {', '.join(supported_vendors)}" if supported_vendors else "GPU: Any"
        info_label = QLabel(f"{vram_text} | {gpu_req_text}")
        info_label.setStyleSheet("color: #b0b0b0; font-size: 8pt;")
        info_label.enterEvent = lambda e: self.show_model_description(model_id)
        info_label.leaveEvent = lambda e: self.clear_description()
        panel_layout.addWidget(info_label)
        
        # AMD warning if needed
        allow_unsupported_gpu = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"
        is_amd_user = self.detected_gpu_vendor == "AMD"
        is_amd_supported = "AMD" in supported_vendors
        is_gpu_unsupported_amd = is_amd_user and not is_amd_supported
        show_warning_amd = allow_unsupported_gpu and is_gpu_unsupported_amd
        
        if show_warning_amd:
            warning_label = QLabel(_("Может не работать на AMD!", "May not work on AMD!"))
            warning_label.setStyleSheet("color: #FF6A6A; font-size: 8pt; font-weight: bold;")
            panel_layout.addWidget(warning_label)
        
        # Action button
        is_installed = model_id in self.installed_models
        
        if is_installed:
            action_button = QPushButton(_("Удалить", "Uninstall"))
            action_button.setObjectName("DangerButton")
            action_button.clicked.connect(lambda: self.confirm_and_start_uninstall(model_id, model_name))
        else:
            install_text = _("Установить", "Install")
            can_install = True
            if is_gpu_unsupported_amd and not allow_unsupported_gpu:
                can_install = False
                install_text = _("Несовместимо с AMD", "Incompatible with AMD")
            
            action_button = QPushButton(install_text)
            action_button.setObjectName("SecondaryButton")
            action_button.setEnabled(can_install)
            if can_install:
                action_button.clicked.connect(lambda: self.confirm_and_start_download(model_id, action_button, model_data))
        
        self.model_action_buttons[model_id] = action_button
        panel_layout.addWidget(action_button)
        
        return panel

    def is_gpu_rtx30_or_40(self):
        """Check if GPU is RTX 30xx or 40xx"""
        force_unsupported_str = os.environ.get("RTX_FORCE_UNSUPPORTED", "0")
        force_unsupported = force_unsupported_str.lower() in ['true', '1', 't', 'y', 'yes']

        if force_unsupported:
            logger.info(_("INFO: RTX_FORCE_UNSUPPORTED=1 - Имитация неподходящей GPU для RTX 30+.", "INFO: RTX_FORCE_UNSUPPORTED=1 - Simulating unsuitable GPU for RTX 30+."))
            return False

        if self.detected_gpu_vendor != "NVIDIA" or not self.gpu_name:
            return False

        name_upper = self.gpu_name.upper()
        if "RTX" in name_upper:
            if any(f" {gen}" in name_upper or name_upper.endswith(gen) or f"-{gen}" in name_upper for gen in ["3050", "3060", "3070", "3080", "3090"]):
                return True
            if any(f" {gen}" in name_upper or name_upper.endswith(gen) or f"-{gen}" in name_upper for gen in ["4050", "4060", "4070", "4080", "4090"]):
                return True
        return False

    def confirm_and_start_download(self, model_id, button_widget, model_data):
        """Show warning for rtx30plus models if GPU doesn't meet requirements"""
        requires_rtx30plus = model_data.get("rtx30plus", False)
        proceed_to_download = True

        if requires_rtx30plus and not self.is_gpu_rtx30_or_40():
            gpu_info = self.gpu_name if self.gpu_name else "не определена"
            if self.detected_gpu_vendor and self.detected_gpu_vendor != "NVIDIA":
                gpu_info = f"{self.detected_gpu_vendor} GPU"

            model_name = model_data.get("name", model_id)
            message = _(
                f"Эта модель ('{model_name}') оптимизирована для видеокарт NVIDIA RTX 30xx/40xx.\n\n"
                f"Ваша видеокарта ({gpu_info}) может не обеспечить достаточной производительности, "
                "что может привести к медленной работе или нестабильности.\n\n"
                "Продолжить установку?",
                f"This model ('{model_name}') is optimized for NVIDIA RTX 30xx/40xx graphics cards.\n\n"
                f"Your graphics card ({gpu_info}) may not provide sufficient performance, "
                "which could lead to slow operation or instability.\n\n"
                "Continue installation?"
            )
            
            reply = QMessageBox.warning(
                self,
                _("Предупреждение", "Warning"),
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            proceed_to_download = reply == QMessageBox.StandardButton.Yes

        if proceed_to_download:
            self.start_download(model_id, button_widget)

    def confirm_and_start_uninstall(self, model_id, model_name):
        """Request confirmation before uninstalling"""
        if not self.local_voice:
            logger.error(_("LocalVoice не инициализирован, удаление невозможно.", "LocalVoice not initialized, uninstallation impossible."))
            QMessageBox.critical(self, _("Ошибка", "Error"), 
                               _("Компонент LocalVoice не доступен.", "LocalVoice component is not available."))
            return

        try:
            if hasattr(self.local_voice, 'is_model_initialized') and self.local_voice.is_model_initialized(model_id):
                logger.warning(f"Попытка удаления инициализированной модели: {model_id}")
                QMessageBox.critical(
                    self,
                    _("Модель Активна", "Model Active"),
                    _(f"Модель '{model_name}' сейчас используется или инициализирована.\n\n"
                      "Пожалуйста, перезапустите приложение полностью, чтобы освободить ресурсы, "
                      "прежде чем удалять эту модель.",
                      f"Model '{model_name}' is currently in use or initialized.\n\n"
                      "Please restart the application completely to free up resources "
                      "before uninstalling this model.")
                )
                return 
        except Exception as e:
            logger.error(f"{_('Ошибка при проверке инициализации модели', 'Error checking model initialization')} {model_id}: {e}")
            QMessageBox.critical(self, _("Ошибка Проверки", "Check Error"), 
                               _(f"Не удалось проверить статус модели '{model_name}'. Удаление отменено.", 
                                 f"Could not check status of model '{model_name}'. Uninstallation cancelled."))
            return

        reply = QMessageBox.warning(
            self,
            _("Подтверждение Удаления", "Confirm Uninstallation"),
            _(f"Вы уверены, что хотите удалить модель '{model_name}'?\n\n"
              "Будут удалены основной пакет модели и все зависимости, которые больше не используются другими установленными моделями (кроме g4f).\n\n"
              "Это действие необратимо!",
              f"Are you sure you want to uninstall the model '{model_name}'?\n\n"
              "The main model package and all dependencies no longer used by other installed models (except g4f) will be removed.\n\n"
              "This action is irreversible!"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.start_uninstall(model_id)

    # =========================================================
    #   ЗАПУСК УСТАНОВКИ  (однопоточный, без statusBar)
    # =========================================================
    def start_download(self, model_id, button_widget):
        # 1)  Кнопка
        if button_widget:
            button_widget.setText(_("Загрузка...", "Downloading..."))
            button_widget.setEnabled(False)

        # 2)  Запускаем установку — окно создастся внутри install()
        success = False
        try:
            success = self.local_voice.download_model(model_id)
        except Exception:
            logger.exception("download_model exception")
        # 3)  Обновляем UI
        self.handle_download_result(success, model_id)

    def start_uninstall(self, model_id):
        button_widget = self.model_action_buttons.get(model_id)
        if button_widget:
            button_widget.setText(_("Удаление...", "Uninstalling..."))
            button_widget.setEnabled(False)

        if not self.local_voice:
            logger.error(f"{_('Неизвестный model_id для удаления:', 'Unknown model_id for uninstallation:')} {model_id}")
            if button_widget:
                button_widget.setText(_("Ошибка", "Error"))
                button_widget.setEnabled(True)
            return

        target_uninstall_func = None
        if model_id in ["low", "low+"]:
            target_uninstall_func = self.local_voice.uninstall_edge_tts_rvc
        elif model_id == "medium":
            target_uninstall_func = self.local_voice.uninstall_fish_speech
        elif model_id in ["medium+", "medium+low"]:
            target_uninstall_func = self.local_voice.uninstall_triton_component
        elif model_id == ["high", "high+low"]:
            target_uninstall_func = self.local_voice.uninstall_f5_tts
        else:
            logger.error(f"Неизвестный model_id для удаления: {model_id}")
            if button_widget:
                button_widget.setText(_("Ошибка", "Error"))
                button_widget.setEnabled(True)
            return

        if not hasattr(self.local_voice, target_uninstall_func.__name__):
            logger.error(f"{_('Метод', 'Method')} {target_uninstall_func.__name__} {_('не найден в LocalVoice.', 'not found in LocalVoice.')}")
            if button_widget:
                button_widget.setText(_("Ошибка", "Error"))
                button_widget.setEnabled(True)
            return

        def uninstall_thread_func():
            success = False
            try:
                success = target_uninstall_func()
            except Exception as e:
                logger.error(f"{_('Ошибка в потоке удаления для', 'Error in uninstall thread for')} {model_id}: {e}")
                logger.error(traceback.format_exc())
            finally:
                QTimer.singleShot(0, lambda: self.handle_uninstall_result(success, model_id))

        uninstall_thread = threading.Thread(target=uninstall_thread_func, daemon=True)
        uninstall_thread.start()

    def handle_download_result(self, success, model_id):
        button_widget = self.model_action_buttons.get(model_id)
        if success:
            self.installed_models.add(model_id)
            logger.info(f"{_('Модель', 'Model')} {model_id} {_('установлена. Перезагрузка и адаптация настроек...', 'installed. Reloading and adapting settings...')}")
            self.load_settings()
            logger.info(_("Настройки перезагружены.", "Settings reloaded."))

            if button_widget:
                button_widget.setText(_("Установлено", "Installed"))
                button_widget.setEnabled(False)

            self.display_installed_models_settings()
            self.save_installed_models_list() 

            if self.on_save_callback:
                 callback_data = {
                    "installed_models": list(self.installed_models),
                    "models_data": self.local_voice_models 
                 }
                 self.on_save_callback(callback_data)
            logger.info(f"{_('Обработка установки', 'Handling installation of')} {model_id} {_('завершена.', 'completed.')}")
        else:
            logger.info(f"{_('Ошибка установки модели', 'Error installing model')} {model_id}.")
            self._create_model_panels()
            button_widget = self.model_action_buttons.get(model_id)
            if button_widget:
                button_widget.setText(_("Ошибка", "Error"))
                button_widget.setEnabled(True) 

    def handle_uninstall_result(self, success, model_id):
        """Update UI after uninstallation"""
        button_widget = self.model_action_buttons.get(model_id)
        model_data = next((m for m in self.local_voice_models if m["id"] == model_id), None)

        if success:
            logger.info(f"{_('Удаление модели', 'Uninstallation of model')} {model_id} {_('завершено успешно.', 'completed successfully.')}")
            if model_id in self.installed_models:
                self.installed_models.remove(model_id)

            if button_widget and model_data:
                install_text = _("Установить", "Install")
                can_install = True

                supported_vendors = model_data.get('gpu_vendor', [])
                allow_unsupported_gpu = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"
                is_amd_user = self.detected_gpu_vendor == "AMD"
                is_amd_supported = "AMD" in supported_vendors
                is_gpu_unsupported_amd = is_amd_user and not is_amd_supported
                if is_gpu_unsupported_amd and not allow_unsupported_gpu:
                    can_install = False
                    install_text = _("Несовместимо с AMD", "Incompatible with AMD")

                button_widget.setText(install_text)
                button_widget.setEnabled(can_install)
                button_widget.setObjectName("SecondaryButton")
                button_widget.setStyleSheet(button_widget.styleSheet())  # Refresh style
                
                try:
                    button_widget.clicked.disconnect()
                except:
                    pass
                    
                if can_install:
                    button_widget.clicked.connect(
                        lambda: self.confirm_and_start_download(model_id, button_widget, model_data)
                    )
            else:
                logger.warning(f"Couldn't find the button for model {model_id} after uninstall.")

            if model_id in self.settings_sections:
                section = self.settings_sections.pop(model_id)
                if section:
                    section.deleteLater()

            if not self.installed_models:
                 self.display_installed_models_settings() 

            self.save_installed_models_list() 
            if self.on_save_callback:
                 callback_data = {"installed_models": list(self.installed_models), "models_data": self.local_voice_models}
                 self.on_save_callback(callback_data)
            self._update_settings_scrollregion() 

        else:
            logger.error(f"{_('Ошибка при удалении модели', 'Error uninstalling model')} {model_id}.")
            QMessageBox.critical(self, _("Ошибка Удаления", "Uninstallation Error"), 
                               _(f"Не удалось удалить модель '{model_id}'.\nСм. лог для подробностей.", 
                                 f"Could not uninstall model '{model_id}'.\nSee log for details."))
            if button_widget:
                button_widget.setText(_("Удалить", "Uninstall"))
                button_widget.setEnabled(True)

    def save_installed_models_list(self):
        try:
            with open(self.installed_models_file, "w", encoding="utf-8") as f:
                for model_id in sorted(list(self.installed_models)):
                    f.write(f"{model_id}\n")
        except Exception as e:
            logger.info(f"{_('Ошибка сохранения списка установленных моделей в', 'Error saving list of installed models to')} {self.installed_models_file}: {e}")

    def show_setting_description(self, key):
        if self.description_label_widget:
            description = self.setting_descriptions.get(key, "")
            self.description_label_widget.setText(description if description else self.default_description_text)

    def show_model_description(self, key):
        if self.description_label_widget:
            description = self.model_descriptions.get(key, "")
            self.description_label_widget.setText(description if description else self.default_description_text)

    def clear_description(self, event=None):
        if self.description_label_widget:
            self.description_label_widget.setText(self.default_description_text)

    def _update_scrollregion(self, canvas):
        """Update scroll region"""
        if canvas:
            canvas.updateGeometry()

    def _update_settings_scrollregion(self, event=None):
        self._update_scrollregion(self.settings_canvas)

    def _update_models_scrollregion(self, event=None):
        self._update_scrollregion(self.models_canvas)

    def save_and_continue(self):
        self.save_settings()

    def save_and_quit(self):
        self.save_settings()
        self.window().close()

    def run(self):
        """For compatibility with tkinter version"""
        self.show()