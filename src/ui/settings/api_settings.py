from utils import _
from presets.api_presets import API_PRESETS, PRICING_SYMBOLS
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QComboBox, QMessageBox


#                         HELPERS
def _mixed_presets(static_presets: dict, custom_presets: dict) -> dict:
    """
    Склеиваем словари так, чтобы встроенные остались нетронутыми.
    Если id уже есть во встроенных, кастомный просто игнорируется.
    """
    merged = static_presets.copy()
    for pid, cust in (custom_presets or {}).items():
        if pid not in merged:
            merged[pid] = cust
    return merged


def _display_name(preset_id: str, preset: dict) -> str:
    """
    Возвращает строку для отображения пользователю: «🕊️ OpenRouter»
    """
    symbol = PRICING_SYMBOLS.get(preset.get("pricing"), "")
    return f"{symbol} {preset.get('name', preset_id)}".strip()


#               ГЛАВНАЯ ФУНКЦИЯ ДЛЯ UI
def setup_api_controls(self, parent):
    """
    Создаёт секцию «API settings».
    Эмодзи в названиях – только для UI, внутри всё хранится по id.
    """
    # ── данные из settings ───────────────────────────────────
    provider_data   = self.settings.get("API_PROVIDER_DATA", {})
    custom_presets  = self.settings.get("CUSTOM_API_PRESETS", {})
    MIXED_PRESETS   = _mixed_presets(API_PRESETS, custom_presets)

    # ── ── ── ── URL builder ── ── ── ──
    def build_dynamic_url(provider_id: str, model: str, key: str) -> str:
        preset = MIXED_PRESETS.get(provider_id, {})
        if not preset:
            return ""

        # 1. шаблон или готовая ссылка
        url_tpl = preset.get("url_tpl") or preset.get("url", "")
        url     = url_tpl.format(model=model) if "{model}" in url_tpl else url_tpl

        # 2. добавить ?key=
        if preset.get("add_key") and key:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}key={key}"

        return url

    # ── ── ── state helpers ── ── ──
    def save_provider_state(provider_id: str):
        if not provider_id:
            return
        provider_data[provider_id] = {
            "NM_API_URL":   api_url_entry.text().strip(),
            "NM_API_MODEL": api_model_entry.text().strip(),
            "NM_API_KEY":   api_key_entry.text().strip(),
            "NM_API_KEY_RES": self.settings.get("NM_API_KEY_RES", ""),
            "NM_API_REQ":   nm_api_req_checkbox.isChecked(),
            "GEMINI_CASE":  gemini_case_checkbox.isChecked(),
        }
        self.settings.set("API_PROVIDER_DATA", provider_data)
        self.settings.save_settings()

    def load_provider_state(provider_id: str, fallback: bool = True):
        stored = provider_data.get(provider_id)
        if stored:
            api_url_entry.setText(stored.get("NM_API_URL", ""))
            api_model_entry.setText(stored.get("NM_API_MODEL", ""))
            api_key_entry.setText(stored.get("NM_API_KEY", ""))

            nm_api_req_checkbox.setChecked(stored.get("NM_API_REQ", False))
            gemini_case_checkbox.setChecked(stored.get("GEMINI_CASE", False))

            # локальные поля
            self._save_setting("NM_API_URL",   stored.get("NM_API_URL", ""))
            self._save_setting("NM_API_MODEL", stored.get("NM_API_MODEL", ""))
            self._save_setting("NM_API_KEY",   stored.get("NM_API_KEY", ""))
            self._save_setting("NM_API_REQ",   stored.get("NM_API_REQ", False))
            self._save_setting("GEMINI_CASE",  stored.get("GEMINI_CASE", False))
            self._save_setting("NM_API_KEY_RES", stored.get("NM_API_KEY_RES", ""))
        elif fallback:
            api_key_entry.setText("")
            self._save_setting("NM_API_KEY", "")
            apply_preset(provider_id)

    # ── ── ── dynamic url updater ── ── ──
    def update_url(force: bool = False):
        provider_id = combo_current_id()
        if provider_id == "custom" and not force:
            return
        url = build_dynamic_url(provider_id,
                                api_model_entry.text().strip(),
                                api_key_entry.text().strip())
        api_url_entry.setText(url)
        self._save_setting("NM_API_URL", url)
        save_provider_state(provider_id)

    # ── ── ── preset-apply ── ── ──
    def apply_preset(provider_id: str):
        preset = MIXED_PRESETS.get(provider_id)
        if not preset:
            return

        api_model_entry.setText(preset.get("model", ""))
        api_key_entry.setText("")  # ключ всегда руками
        nm_api_req_checkbox.setChecked(preset.get("nm_api_req", False))
        gemini_case_checkbox.setChecked(preset.get("gemini_case", False))

        self._save_setting("NM_API_MODEL",  preset.get("model", ""))
        self._save_setting("NM_API_KEY",    "")
        self._save_setting("NM_API_REQ",    preset.get("nm_api_req", False))
        self._save_setting("GEMINI_CASE",   preset.get("gemini_case", False))

        update_url(force=True)

    # ── ── ── Combo helpers ── ── ──
    DISPLAY2ID = {}      # отображаемое → id
    ID2DISPLAY = {}      # id → отображаемое

    def combo_current_id() -> str:
        return DISPLAY2ID.get(api_provider_combo.currentText(), "custom")

    # ── ── ── готовим список провайдеров ── ── ──
    builtin_pairs = [(pid, _display_name(pid, API_PRESETS[pid]))
                     for pid in API_PRESETS]
    builtin_pairs.append(("custom", "Custom"))

    custom_pairs = [(pid, pid) for pid in custom_presets.keys()]
    provider_pairs   = builtin_pairs + custom_pairs
    separator_index  = len(builtin_pairs)

    # заполняем отображ/словарь
    for pid, text in provider_pairs:
        DISPLAY2ID[text] = pid
        ID2DISPLAY[pid]  = text

    # ── ── ── FORM CONFIG для create_settings_section ── ── ──
    config = [
        {'label': _('Провайдер', 'Provider'),
         'key': 'API_PROVIDER',
         'type': 'combobox',
         'options': [p[1] for p in provider_pairs],
         'default': 'Custom',
         'command': lambda: on_provider_changed(),
         'widget_name': 'api_provider_combo'},
        {'type': 'button_group',
         'buttons': [
             {'label': _('Сохранить / обновить пресет', 'Save / update preset'),
              'command': lambda: _btn_save_preset()},
             {'label': _('Удалить пресет', 'Delete preset'),
              'command': lambda: _btn_delete_preset()},
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
        {'label': _('Через Request', 'Using Request'),
         'key': 'NM_API_REQ',
         'type': 'checkbutton',
         'widget_name': 'nm_api_req_checkbox'},
        {'label': _('Структура Гемини', 'Gemini Structure'),
         'key': 'GEMINI_CASE',
         'type': 'checkbutton',
         'default_checkbutton': False,
         'widget_name': 'gemini_case_checkbox',
         'tooltip':_("Формат сообщений gemini отличается от других, поэтому требуется преобразование",
                     "Gemini message format differs from others, so enable conversion")},
        {'label': _('Резервные ключи', 'Reserve keys'),
         'key': 'NM_API_KEY_RES',
         'type': 'textarea',
         'hide': bool(self.settings.get("HIDE_PRIVATE")),
         'default': "",
         'widget_name': 'nm_api_key_res_label'},
    ]

    # ── ── ── создаём секцию ── ── ──
    self.create_settings_section(parent,
                                 _("Настройки API", "API settings"),
                                 config)

    # ── ── ── виджеты ── ── ──
    api_provider_combo: QComboBox = getattr(self, 'api_provider_combo')
    api_model_entry   = getattr(self, 'api_model_entry')
    api_url_entry     = getattr(self, 'api_url_entry')
    api_key_entry     = getattr(self, 'api_key_entry')
    gemini_case_checkbox = getattr(self, 'gemini_case_checkbox')
    nm_api_req_checkbox  = getattr(self, 'nm_api_req_checkbox')

    # ── вставляем визуальный разделитель ──
    api_provider_combo.insertSeparator(separator_index)

    # ── живые обновления ссылки ──
    api_model_entry.textChanged.connect(lambda _: update_url())
    api_key_entry.textChanged.connect(lambda _: update_url())

    # ── реакция на выбор провайдера ──
    self._last_provider = combo_current_id()

    def on_provider_changed():
        save_provider_state(self._last_provider)
        new_id = combo_current_id()
        load_provider_state(new_id, fallback=True)
        self._last_provider = new_id
        update_url(force=True)

    api_provider_combo.currentIndexChanged.connect(lambda _: on_provider_changed())

    # ── ── ── стартовое восстановление ── ── ──
    QTimer.singleShot(0, lambda: load_provider_state(combo_current_id(), fallback=False))
    QTimer.singleShot(0, lambda: update_url(force=True))

    # ────────────────────────────────────────────────────
    #        SAVE / DELETE   (custom preset)
    # ────────────────────────────────────────────────────
    def _btn_save_preset():
        from PyQt6.QtWidgets import QInputDialog
        cur_id = combo_current_id()

        # 1. Получаем желаемое имя/ID
        if cur_id in API_PRESETS or cur_id == "custom":
            name, ok = QInputDialog.getText(
                self, _("Имя пресета", "Preset name"),
                _("Название нового пресета:", "New preset name:"))
            if not ok or not name.strip():
                return
            preset_id = name.strip()
        else:
            preset_id = cur_id  # пользователь решил обновить свой же пресет

        # 2. Проверяем конфликт с встроенными
        if preset_id in API_PRESETS:
            QMessageBox.warning(
                self,
                _("Конфликт", "Conflict"),
                _("Такой ID зарезервирован для встроенного пресета.\n"
                  "Выберите другое имя.", "This ID is reserved for builtin preset.\nChoose another name.")
            )
            return
        # 2. сохраняем
        custom_presets[preset_id] = {
            "url":   api_url_entry.text().strip(),
            "model": api_model_entry.text().strip(),
            "pricing": "mixed"
        }
        self.settings.set("CUSTOM_API_PRESETS", custom_presets)
        self.settings.save_settings()
        MIXED_PRESETS.update({preset_id: custom_presets[preset_id]})

        # 3. добавляем в ComboBox если нового не было
        if preset_id not in [DISPLAY2ID.get(api_provider_combo.itemText(i))
                             for i in range(api_provider_combo.count())]:
            api_provider_combo.addItem(preset_id)   # кастом без эмодзи
            DISPLAY2ID[preset_id] = preset_id
            ID2DISPLAY[preset_id] = preset_id

            if hasattr(self, 'HC_PROVIDER'):
                getattr(self, 'HC_PROVIDER').addItem(preset_id)

        # 4. выделяем
        api_provider_combo.setCurrentText(ID2DISPLAY[preset_id])
        save_provider_state(preset_id)

    def _btn_delete_preset():
        from PyQt6.QtWidgets import QMessageBox
        cur_id = combo_current_id()
        if cur_id in custom_presets:
            if QMessageBox.question(
                    self, _("Удалить", "Delete"),
                    _("Удалить пресет «{}»?".format(cur_id),
                      "Delete preset «{}»?".format(cur_id)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

            # 1. удаляем
            custom_presets.pop(cur_id, None)
            provider_data.pop(cur_id, None)
            self.settings.set("CUSTOM_API_PRESETS", custom_presets)
            self.settings.set("API_PROVIDER_DATA", provider_data)
            self.settings.save_settings()

            # 2. из ComboBox
            idx = api_provider_combo.findText(ID2DISPLAY[cur_id])
            if idx >= 0:
                api_provider_combo.removeItem(idx)

                if hasattr(self, 'HC_PROVIDER'):
                    getattr(self, 'HC_PROVIDER').removeItem(idx)

            api_provider_combo.setCurrentText('Custom')