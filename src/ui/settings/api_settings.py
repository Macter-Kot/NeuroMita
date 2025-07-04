from utils import _
from presets.api_presets import API_PRESETS
from PyQt6.QtCore import QTimer          # локальный импорт, чтобы не ломать другие модули

def setup_api_controls(self, parent):

    # ───────────────────────────────────────────────
    #      Хранилище «настройки-на-провайдера»
    # ───────────────────────────────────────────────
    provider_data = self.settings.get("API_PROVIDER_DATA", {})  # {prov:{field:val}}

    def save_provider_state(provider_name: str):
        """Сохраняет текущие поля для указанного провайдера."""
        if not provider_name:
            return
        provider_data[provider_name] = {
            "NM_API_URL":   api_url_entry.text().strip(),
            "NM_API_MODEL": api_model_entry.text().strip(),
            "NM_API_KEY":   api_key_entry.text().strip(),
        }
        # моментально в settings (без вызова all_settings_actions)
        self.settings.set("API_PROVIDER_DATA", provider_data)
        self.settings.save_settings()

    def load_provider_state(provider_name: str, fallback: bool = True):
        stored = provider_data.get(provider_name)
        if stored:
            api_url_entry.setText(stored.get("NM_API_URL", ""))
            api_model_entry.setText(stored.get("NM_API_MODEL", ""))
            api_key_entry.setText(stored.get("NM_API_KEY", ""))
            self._save_setting("NM_API_URL",   api_url_entry.text())
            self._save_setting("NM_API_MODEL", api_model_entry.text())
            self._save_setting("NM_API_KEY",   api_key_entry.text())
        elif fallback:
            api_key_entry.setText("")                 
            self._save_setting("NM_API_KEY", "")
            apply_preset(provider_name)

    # ───────────────────────────────────────────────
    #         Построение URL
    # ───────────────────────────────────────────────
    def build_dynamic_url(provider: str, model: str, key: str) -> str:
        if provider == "Google AI Studio":
            base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            return f"{base}?key={key}" if key else base
        return API_PRESETS.get(provider, {}).get("url", "")

    def update_url(force: bool = False):
        prov  = api_provider_combo.currentText()
        if prov == "Custom" and not force:
            return                      # Custom – URL только ручной
        url = build_dynamic_url(prov,
                                api_model_entry.text().strip(),
                                api_key_entry.text().strip())
        api_url_entry.setText(url)
        self._save_setting("NM_API_URL", url)
        save_provider_state(prov)

    # ───────────────────────────────────────────────
    #        Пресет при выборе провайдера
    # ───────────────────────────────────────────────
    self._last_provider = self.settings.get("API_PROVIDER", "Custom")

    def on_provider_changed():
        # 1) сохраняем старого
        save_provider_state(self._last_provider)
        # 2) загружаем нового
        new_prov = api_provider_combo.currentText()
        load_provider_state(new_prov, fallback=True)
        self._last_provider = new_prov
        update_url(force=True)          # уточняем ссылку

    def apply_preset(provider_name: str):
        preset = API_PRESETS.get(provider_name)
        if not preset:
            return
        api_model_entry.setText(preset["model"])
        api_key_entry.setText("")                     # <-- NEW (очистка)
        self._save_setting("NM_API_MODEL", preset["model"])
        self._save_setting("NM_API_KEY", "")
        update_url(force=True)

    
    # ───────────────────────────────────────────────
    #   формируем ЕДИНЫЙ список провайдеров (без дублей)
    # ───────────────────────────────────────────────
    provider_names = list(API_PRESETS.keys()) + ['Custom', 'Google AI Studio', 'ProxiApi']
    seen = set(); provider_names = [p for p in provider_names if not (p in seen or seen.add(p))]

    common_config = [
        {'label': _('Провайдер', 'Provider'),
         'key': 'API_PROVIDER',
         'type': 'combobox',
         'options': provider_names,
         'default': 'Custom',
         'command': on_provider_changed,
         'widget_name': 'api_provider_combo'},

        # ---- URL / MODEL / KEY ------------------------------------
        {'label': _('Ссылка', 'URL'),
         'key': 'NM_API_URL',
         'type': 'entry',
         'widget_name': 'api_url_entry'},

        {'label': _('Модель', 'Model'),
         'key': 'NM_API_MODEL',
         'type': 'entry',
         'widget_name': 'api_model_entry'},

        {'label': _('Ключ', 'Key'),
         'key': 'NM_API_KEY',
         'type': 'entry',
         'widget_name': 'api_key_entry',
         'hide': True},

        # ---- остаётся без изменений -------------------------------
        {'label': _('Резервные ключи', 'Reserve keys'),
         'key': 'NM_API_KEY_RES',
         'type': 'text',
         'hide': bool(self.settings.get("HIDE_PRIVATE")),
         'default': ""},

        {'label': _('Через Request', 'Using Request'),
         'key': 'NM_API_REQ',
         'type': 'checkbutton'},

        {'label': _('Гемини для ProxiAPI', 'Gemini for ProxiAPI'),
         'key': 'GEMINI_CASE',
         'type': 'checkbutton',
         'default_checkbutton': False,
         'widget_name': 'gemini_case_checkbox'},
    ]

    self.create_settings_section(parent,
                                 _("Настройки API", "API settings"),
                                 common_config)

    # ---------- ссылки на виджеты ----------
    api_provider_combo      = getattr(self, 'api_provider_combo')
    api_model_entry         = getattr(self, 'api_model_entry')
    api_url_entry           = getattr(self, 'api_url_entry')
    api_key_entry           = getattr(self, 'api_key_entry')
    gemini_case_checkbox    = getattr(self, 'gemini_case_checkbox')

    def _auto_gemini_case(provider_name: str):
        auto_state = (provider_name == "Google AI Studio")
        gemini_case_checkbox.setChecked(auto_state)
        self._save_setting("GEMINI_CASE", auto_state)

    # подключаем «живой» сигнал
    api_provider_combo.currentTextChanged.connect(_auto_gemini_case)

    # вызываем один раз для текущего выбранного
    _auto_gemini_case(api_provider_combo.currentText())

    # instant-update URL
    api_model_entry.textChanged.connect(lambda _: update_url())
    api_key_entry.textChanged.connect(lambda _: update_url())

    # восстановление при старте
    QTimer.singleShot(0, lambda: load_provider_state(api_provider_combo.currentText(), fallback=False))
    QTimer.singleShot(0, lambda: update_url(force=True))