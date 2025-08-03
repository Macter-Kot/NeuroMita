from presets.api_presets import API_PRESETS
from utils import getTranslationVariant as _


def setup_history_compressor_controls(self, parent):
    """Создает секцию настроек специально для чата."""
    settings_config = [
        {'label': _('Сжимать историю при достижении лимита', 'Compress history on limit'),
         'key': 'ENABLE_HISTORY_COMPRESSION_ON_LIMIT', 'type': 'checkbutton',
         'default_checkbutton': False,
         'tooltip': _('Включить автоматическое сжатие истории чата, когда количество сообщений превышает лимит.',
                      'Enable automatic chat history compression when message count exceeds a limit.')},
        {'label': _('Периодическое сжатие истории', 'Periodic history compression'),
         'key': 'ENABLE_HISTORY_COMPRESSION_PERIODIC', 'type': 'checkbutton',
         'default_checkbutton': False,
         'tooltip': _('Включить автоматическое сжатие истории чата через заданные интервалы.',
                      'Enable automatic chat history compression at specified intervals.')},
        {'label': _('Интервал периодического сжатия (сообщения)', 'Periodic compression interval (messages)'),
         'key': 'HISTORY_COMPRESSION_PERIODIC_INTERVAL', 'type': 'entry',
         'default': 20, 'validation': self.validate_positive_integer,
         'tooltip': _('Количество сообщений, после которых будет произведено периодическое сжатие истории.',
                      'Number of messages after which periodic history compression will occur.')},
        {'label': _('Шаблон промпта для сжатия', 'Compression prompt template'),
         'key': 'HISTORY_COMPRESSION_PROMPT_TEMPLATE', 'type': 'entry',
         'default': "Prompts/System/compression_prompt.txt",
         'tooltip': _('Путь к файлу шаблона промпта, используемого для сжатия истории.',
                      'Path to the prompt template file used for history compression.')},
        {'label': _('Процент для сжатия', 'Percent to compress'),
         'key': 'HISTORY_COMPRESSION_MIN_PERCENT_TO_COMPRESS', 'type': 'entry',
         'default': 0.85, 'validation': self.validate_float_0_1,
         'tooltip': _('Минимальное количество сообщений в истории, необходимое для запуска процесса сжатия.',
                      'Minimum number of messages in history required to trigger compression.')},
        {'label': _('Цель вывода сжатой истории', 'Compressed history output target'),
         'key': 'HISTORY_COMPRESSION_OUTPUT_TARGET', 'type': 'combobox',
         'options': ['history','memory'],
         'default': "history",
         'tooltip': _('Куда помещать результат сжатия истории (например, "memory", "summary_message").',
                      'Where to place the compressed history output (e.g., "memory", "summary_message").')},
    ]
    # --- список провайдеров, которым уже управляет setup_api_controls
    provider_names = list(API_PRESETS.keys()) \
                     + ['Custom', 'Google AI Studio', 'ProxiApi'] \
                     + list(self.settings.get("CUSTOM_API_PRESETS", {}).keys())
    provider_names = list(dict.fromkeys(provider_names))  # убираем дубликаты
    provider_names.insert(0, _("Текущий", "Current"))  # «не переключать»

    settings_config += [
        {'label': _('Провайдер для сжатия', 'Provider for compression'),
         'key': 'HC_PROVIDER',  # History-Compression provider
         'type': 'combobox',
         'options': provider_names,
         'default': _('Текущий', 'Current')},
    ]
    self.create_settings_section(parent,
                                 _("Настройки сжатия истории", "History compression Settings"),
                                 settings_config)