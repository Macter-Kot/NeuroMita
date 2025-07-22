from utils import getTranslationVariant as _

def get_default_model_structure():
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
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
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
                {"key": "silero_put_yo", "label": _("Буква Ё Silero", "Silero Letter Yo"), "type": "checkbutton", "options": {"default": True}},
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
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
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
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
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
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
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
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
                {"key": "seed", "label": _("Seed", "Seed"), "type": "entry", "options": {"default": "0"}},
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
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
                {"key": "volume", "label": _("Громкость (volume)", "Volume"), "type": "entry", "options": {"default": "1.0"}},
            ]
        }
    ]