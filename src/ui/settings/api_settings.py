# api_controls.py
from utils import _
from presets.api_presets import API_PRESETS
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QComboBox

def setup_api_controls(self, parent):
    """
    Создаёт секцию «API settings» с разделителем между
    встроенными и пользовательскими пресетами.
    """
    # ── данные из settings ───────────────────────────────────
    provider_data = self.settings.get("API_PROVIDER_DATA", {})
    custom_api_presets = self.settings.get("CUSTOM_API_PRESETS", {})
    MIXED_PRESETS = _mixed_presets(API_PRESETS, custom_api_presets)

    #                     HELPERS
    def save_provider_state(provider_name: str):
        if not provider_name:
            return
        provider_data[provider_name] = {
            "NM_API_URL": api_url_entry.text().strip(),
            "NM_API_MODEL": api_model_entry.text().strip(),
            "NM_API_KEY": api_key_entry.text().strip(),
            "NM_API_KEY_RES": self.settings.get("NM_API_KEY_RES", ""),
            "NM_API_REQ": nm_api_req_checkbox.isChecked(),
            "GEMINI_CASE": gemini_case_checkbox.isChecked(),
        }
        self.settings.set("API_PROVIDER_DATA", provider_data)
        self.settings.save_settings()

    def load_provider_state(provider_name: str, fallback: bool = True):
        stored = provider_data.get(provider_name)
        if stored:
            api_url_entry.setText(stored.get("NM_API_URL", ""))
            api_model_entry.setText(stored.get("NM_API_MODEL", ""))
            api_key_entry.setText(stored.get("NM_API_KEY", ""))

            nm_api_req_checkbox.setChecked(stored.get("NM_API_REQ", False))
            gemini_case_checkbox.setChecked(stored.get("GEMINI_CASE", False))

            self._save_setting("NM_API_URL", api_url_entry.text())
            self._save_setting("NM_API_MODEL", api_model_entry.text())
            self._save_setting("NM_API_KEY", api_key_entry.text())
            self._save_setting("NM_API_REQ", nm_api_req_checkbox.isChecked())
            self._save_setting("GEMINI_CASE", gemini_case_checkbox.isChecked())
            self._save_setting("NM_API_KEY_RES", stored.get("NM_API_KEY_RES", ""))
        elif fallback:
            api_key_entry.setText("")
            self._save_setting("NM_API_KEY", "")
            apply_preset(provider_name)

    #             URL builder (динамический)
    def build_dynamic_url(provider: str, model: str, key: str) -> str:
        if provider == "️🕊️️/💲Google AI Studio":
            base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            return f"{base}?key={key}" if key else base
        elif provider == "️️💲 ProxiApi (for google)":
            base = f"https://api.proxyapi.ru/google/v1/models/{model}:generateContent"
            return base
        return MIXED_PRESETS.get(provider, {}).get("url", "")

    def update_url(force: bool = False):
        prov = api_provider_combo.currentText()
        if prov == "Custom" and not force:
            return
        url = build_dynamic_url(prov,
                                api_model_entry.text().strip(),
                                api_key_entry.text().strip())
        api_url_entry.setText(url)
        self._save_setting("NM_API_URL", url)
        save_provider_state(prov)

    #                    PRESET LOGIC
    self._last_provider = self.settings.get("API_PROVIDER", "Custom")

    def on_provider_changed():
        save_provider_state(self._last_provider)
        new_prov = api_provider_combo.currentText()
        load_provider_state(new_prov, fallback=True)
        self._last_provider = new_prov
        update_url(force=True)

    # --- ИЗМЕНЕНИЯ ЗДЕСЬ: Обновлена функция apply_preset ---
    def apply_preset(provider_name: str):
        preset = MIXED_PRESETS.get(provider_name)
        if not preset:
            return

        # Основные поля
        api_model_entry.setText(preset.get("model", ""))
        api_key_entry.setText("")  # Ключ всегда сбрасываем при применении пресета

        # Дополнительные поля (чекбоксы) с дефолтным значением False
        nm_api_req_val = preset.get("nm_api_req", False)
        gemini_case_val = preset.get("gemini_case", False)

        nm_api_req_checkbox.setChecked(nm_api_req_val)
        gemini_case_checkbox.setChecked(gemini_case_val)

        # Сохраняем все применённые значения
        self._save_setting("NM_API_MODEL", preset.get("model", ""))
        self._save_setting("NM_API_KEY", "")
        self._save_setting("NM_API_REQ", nm_api_req_val)
        self._save_setting("GEMINI_CASE", gemini_case_val)

        # Обновляем URL в последнюю очередь, т.к. он может зависеть от других полей
        update_url(force=True)

    #            SAVE / DELETE  (кастомный пресет)
    def _btn_save_preset():
        from PyQt6.QtWidgets import QInputDialog
        cur_provider = api_provider_combo.currentText()

        # 1.  имя, под которым будем хранить
        if cur_provider in list(API_PRESETS.keys()) + ['Custom']:
            name, ok = QInputDialog.getText(
                self, _("Имя пресета", "Preset name"),
                _("Название нового пресета:", "New preset name:"))
            if not ok or not name.strip():
                return
            preset_name = name.strip()
        else:
            preset_name = cur_provider  # перезаписываем уже существующий пользовательский

        # 2.  кладём в custom-хранилище
        custom_api_presets[preset_name] = {
            "url": api_url_entry.text().strip(),
            "model": api_model_entry.text().strip()
        }
        self.settings.set("CUSTOM_API_PRESETS", custom_api_presets)
        self.settings.save_settings()
        MIXED_PRESETS.update({preset_name: custom_api_presets[preset_name]})

        # 3.  добавляем в ComboBox (ниже разделителя, если он не был)
        if preset_name not in [api_provider_combo.itemText(i)
                               for i in range(api_provider_combo.count())]:
            api_provider_combo.addItem(preset_name)

            if hasattr(self, 'HC_PROVIDER'):
                hc_provider_combo = getattr(self, 'HC_PROVIDER')
                hc_provider_combo.addItem(preset_name)

        # 4.  выделяем
        api_provider_combo.setCurrentText(preset_name)
        save_provider_state(preset_name)

    def _btn_delete_preset():
        cur_provider = api_provider_combo.currentText()
        if cur_provider in custom_api_presets:
            from PyQt6.QtWidgets import QMessageBox
            if QMessageBox.question(
                    self, _("Удалить", "Delete"),
                    _("Удалить пресет «{}»?".format(cur_provider),
                      "Delete preset «{}»?".format(cur_provider)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

            # 1.  удаляем из хранилищ
            custom_api_presets.pop(cur_provider, None)
            provider_data.pop(cur_provider, None)
            self.settings.set("CUSTOM_API_PRESETS", custom_api_presets)
            self.settings.set("API_PROVIDER_DATA", provider_data)
            self.settings.save_settings()

            # 2.  убираем из ComboBox
            idx = api_provider_combo.findText(cur_provider)
            if idx >= 0:
                api_provider_combo.removeItem(idx)

                if hasattr(self, 'HC_PROVIDER'):
                    hc_provider_combo = getattr(self, 'HC_PROVIDER')
                    hc_provider_combo.removeItem(idx)

            api_provider_combo.setCurrentText('Custom')

    #       СТРОИМ ComboBox cо «встроенными / кастомными»
    builtin_providers = list(API_PRESETS.keys()) + ['Custom']
    builtin_seen = set();
    builtin_providers = [p for p in builtin_providers
                         if not (p in builtin_seen or builtin_seen.add(p))]

    custom_providers = list(custom_api_presets.keys())

    # итоговый список + индекс разделителя
    provider_names = builtin_providers + custom_providers
    separator_index = len(builtin_providers)

    #            FORM CONFIG FOR create_settings_section
    common_config = [
        {'label': _('Провайдер', 'Provider'),
         'key': 'API_PROVIDER',
         'type': 'combobox',
         'options': provider_names,
         'default': 'Custom',
         'command': on_provider_changed,
         'widget_name': 'api_provider_combo'},
        {'type': 'button_group',
         'buttons': [
             {'label': _('Сохранить / обновить пресет', 'Save / update preset'),
              'command': _btn_save_preset},
             {'label': _('Удалить пресет', 'Delete preset'),
              'command': _btn_delete_preset},
         ]},
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

        {'label': _('Резервные ключи', 'Reserve keys'),
         'key': 'NM_API_KEY_RES',
         'type': 'text',
         'hide': bool(self.settings.get("HIDE_PRIVATE")),
         'default': "",
         'widget_name': 'nm_api_key_res_label'},

        {'label': _('Через Request', 'Using Request'),
         'key': 'NM_API_REQ',
         'type': 'checkbutton',
         'widget_name': 'nm_api_req_checkbox'},

        {'label': _('Структура Гемини', 'Gemini Structure'),
         'key': 'GEMINI_CASE',
         'type': 'checkbutton',
         'default_checkbutton': False,
         'widget_name': 'gemini_case_checkbox',
         'tooltip':_("Формат сообщений гемини (напрямую) отличается от других, потому требуется преобразование включаемое данной галкой",
                     "The format of gemini messages (directly) is different from others, so the transformation enabled by this checkbox is required")},
    ]

    # ── создаём UI секцию ───────────────────────────────────
    self.create_settings_section(parent,
                                 _("Настройки API", "API settings"),
                                 common_config)

    # ── ссылки на виджеты (после создания) ─────────────────
    api_provider_combo = getattr(self, 'api_provider_combo')  # type: QComboBox
    api_model_entry = getattr(self, 'api_model_entry')
    api_url_entry = getattr(self, 'api_url_entry')
    api_key_entry = getattr(self, 'api_key_entry')
    gemini_case_checkbox = getattr(self, 'gemini_case_checkbox')
    nm_api_req_checkbox = getattr(self, 'nm_api_req_checkbox')

    # ── вставляем «визуальный» разделитель в ComboBox ───────
    api_provider_combo.insertSeparator(separator_index)

    # ── живые обновления URL ────────────────────────────────
    api_model_entry.textChanged.connect(lambda _: update_url())
    api_key_entry.textChanged.connect(lambda _: update_url())

    # ── восстановление при старте ───────────────────────────
    QTimer.singleShot(0, lambda: load_provider_state(api_provider_combo.currentText(), fallback=False))
    QTimer.singleShot(0, lambda: update_url(force=True))


# ─────────────────────────────────────────────────────────────
#                   UTILS
# ─────────────────────────────────────────────────────────────
def _mixed_presets(static_presets: dict, custom_presets: dict) -> dict:
    """
    Склеиваем статические и пользовательские пресеты так,
    чтобы «кастомные» имели приоритет.
    """
    merged = static_presets.copy()
    merged.update(custom_presets or {})
    return merged