from utils import getTranslationVariant as _

def setup_general_settings_control(self, parent):
    general_config = [
        # ─────────── Под-секция 1 ───────────
        {'label': _('Настройки сообщений', 'Message settings'), 'type': 'subsection'},
        {'label': _('Промты раздельно', 'Separated prompts'), 'key': 'SEPARATE_PROMPTS',
         'type': 'checkbutton', 'default_checkbutton': True},

        {'label': _('Лимит сообщений', 'Message limit'), 'key': 'MODEL_MESSAGE_LIMIT',
         'type': 'entry', 'default': 40,
         'tooltip': _('Сколько сообщений будет помнить мита', 'How much messages Mita will remember')},
        {'label': _('Сохранять утерянную историю ', 'Save lost history'),
         'key': 'GPT4FREE_LAST_ATTEMPT', 'type': 'checkbutton', 'default_checkbutton': False},

        {'label': _('Кол-во попыток', 'Attempt count'), 'key': 'MODEL_MESSAGE_ATTEMPTS_COUNT',
         'type': 'entry', 'default': 3},
        {'label': _('Время между попытками', 'time between attempts'),
         'key': 'MODEL_MESSAGE_ATTEMPTS_TIME', 'type': 'entry', 'default': 0.20},
        {'label': _('Включить стриминговую передачу', 'Enable Streaming'), 'key': 'ENABLE_STREAMING',
         'type': 'checkbutton',
         'default_checkbutton': False},
        {'label': _('Использовать gpt4free последней попыткой ', 'Use gpt4free as last attempt'),
         'key': 'GPT4FREE_LAST_ATTEMPT', 'type': 'checkbutton', 'default_checkbutton': False},

        {'type': 'end'},  # ── конец подп-секции 1 ──

        # ─────────── Под-секция 2 ───────────
        {'label': _('Настройки ожидания', 'Waiting settings'), 'type': 'subsection'},
        {'label': _('Время ожидания текста (сек)', 'Text waiting time (sec)'),
         'key': 'TEXT_WAIT_TIME', 'type': 'entry', 'default': 40,
         'tooltip': _('время ожидания ответа', 'response waiting time')},
        {'label': _('Время ожидания звука (сек)', 'Voice waiting time (sec)'),
         'key': 'VOICE_WAIT_TIME', 'type': 'entry', 'default': 40,
         'tooltip': _('время ожидания озвучки', 'voice generation waiting time')},

        {'type': 'end'},  # ── конец подп-секции 2 ──

        # ─────────── Под-секция 3 ───────────
        {'label': _('Настройки генерации текста', 'Text Generation Settings'), 'type': 'subsection'},

        # ───────── Max-tokens ─────────
        {'label': _('Макс. токенов в ответе', 'Max response tokens'),
        'key': 'MODEL_MAX_RESPONSE_TOKENS',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_MAX_RESPONSE_TOKENS',
        'toggle_default': self.settings.get('USE_MODEL_MAX_RESPONSE_TOKENS', True),
        'default': 2500,
        'validation': self.validate_positive_integer,
        'tooltip': _('Максимальное количество токенов в ответе модели',
                    'Maximum number of tokens in the model response')},

        # ——— Temperature (всегда доступна, без depends)

        {'label': _('Температура', 'Temperature'), 'key': 'MODEL_TEMPERATURE',
         'type': 'entry', 'default': 0.5, 'validation': self.validate_float_0_to_2,
         'tooltip': _('Креативность ответа (0.0 = строго, 2.0 = очень творчески)',
                      'Creativity of response (0.0 = strict, 2.0 = very creative)')},

        # ───────── Top-K ─────────
        {'label': _('Top-K', 'Top-K'),
        'key': 'MODEL_TOP_K',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_TOP_K',
        'toggle_default': self.settings.get('USE_MODEL_TOP_K', True),
        'default': 0,
        'validation': self.validate_positive_integer_or_zero,
        'tooltip': _('Ограничивает выбор токенов K наиболее вероятными (0 = отключено)',
                    'Limits token selection to K most likely (0 = disabled)')},

        # ───────── Top-P ─────────
        {'label': _('Top-P', 'Top-P'),
        'key': 'MODEL_TOP_P',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_TOP_P',
        'toggle_default': self.settings.get('USE_MODEL_TOP_P', True),
        'default': 1.0,
        'validation': self.validate_float_0_to_1,
        'tooltip': _('Ограничивает выбор токенов по кумулятивной вероятности (0.0-1.0)',
                    'Limits token selection by cumulative probability (0.0-1.0)')},

        # ───────── Thinking budget ─────────
        {'label': _('Бюджет размышлений', 'Thinking budget'),
        'key': 'MODEL_THINKING_BUDGET',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_THINKING_BUDGET',
        'toggle_default': self.settings.get('USE_MODEL_THINKING_BUDGET', False),
        'default': 0.0,
        'validation': self.validate_float_minus2_to_2,
        'tooltip': _('Параметр, влияющий на глубину "размышлений" модели (зависит от модели)',
                    'Parameter influencing the depth of model "thoughts" (model-dependent)')},

        # ───────── Presence penalty ─────────
        {'label': _('Штраф присутствия', 'Presence penalty'),
        'key': 'MODEL_PRESENCE_PENALTY',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_PRESENCE_PENALTY',
        'toggle_default': self.settings.get('USE_MODEL_PRESENCE_PENALTY', False),
        'default': 0.0,
        'validation': self.validate_float_minus2_to_2,
        'tooltip': _('Штраф за использование новых токенов (-2.0 = поощрять новые, 2.0 = сильно штрафовать)',
                    'Penalty for using new tokens (-2.0 = encourage new, 2.0 = strongly penalize)')},

        # ───────── Frequency penalty ─────────
        {'label': _('Штраф частоты', 'Frequency penalty'),
        'key': 'MODEL_FREQUENCY_PENALTY',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_FREQUENCY_PENALTY',
        'toggle_default': self.settings.get('USE_MODEL_FREQUENCY_PENALTY', False),
        'default': 0.0,
        'validation': self.validate_float_minus2_to_2,
        'tooltip': _('Штраф за частоту использования токенов (-2.0 = поощрять повторение, 2.0 = сильно штрафовать)',
                    'Penalty for the frequency of token usage (-2.0 = encourage repetition, 2.0 = strongly penalize)')},

        # ───────── Log-probability ─────────
        {'label': _('Лог вероятности', 'Log probability'),
        'key': 'MODEL_LOG_PROBABILITY',
        'type': 'entry',
        'toggle_key': 'USE_MODEL_LOG_PROBABILITY',
        'toggle_default': self.settings.get('USE_MODEL_LOG_PROBABILITY', False),
        'default': 0.0,
        'validation': self.validate_float_minus2_to_2,
        'tooltip': _('Параметр, влияющий на логарифмическую вероятность выбора токенов (-2.0 = поощрять, 2.0 = штрафовать)',
                    'Parameter influencing the logarithmic probability of token selection (-2.0 = encourage, 2.0 = penalize)')},

        # ───────── Tools use ─────────
        {'label': _('Вызов инструментов', 'Tools use'),
         'key': 'TOOLS_ON',
         'type': 'checkbutton',
         'default_checkbutton': False,
         'tooltip': _(
             'Позволяет использовать инструменты такие как поиск в сети',
             'Allow using tools like seacrh')},
        {'label': _("Режим инструментов","Tools mode"), 'key': 'TOOLS_MODE', 'type': 'combobox',
         'options': ["native", "legacy"], 'default': "native", "depends_on": "TOOLS_ON",
         'tooltip': _('Native - использует вшитые возможности модели, legacy - добавляет промпт и ловит вызов вручную',
                    'Native - using buit-in tools, legacy - using own prompts and handler')},

        {'type': 'end'},  # ── конец под-секции 3 ──
    ]

    self.create_settings_section(
        parent,
        _("Общие настройки моделей", "General settings for models"),
        general_config,
        icon_name='fa5s.cogs'
    )