# ui/settings/api_controls.py
from utils import _
from presets.api_presets import API_PRESETS
from PyQt6.QtCore    import QTimer, Qt, QSize
from PyQt6.QtGui     import (QPainter, QPixmap, QColor, QFont,
                              QIcon, QPalette, QFontMetrics )
from PyQt6.QtWidgets import (QComboBox, QMessageBox,
                              QStyledItemDelegate, QStyle)
import qtawesome as qta


# ──────────────────────────────────────────────────────────
#                  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ──────────────────────────────────────────────────────────
def _mixed_presets(static_presets: dict, custom_presets: dict) -> dict:
    """
    Возвращает объединение встроенных и пользовательских пресетов
    (пользовательские НЕ перекрывают встроенные).
    """
    merged = static_presets.copy()
    for pid, cust in (custom_presets or {}).items():
        if pid not in merged:
            merged[pid] = cust
    return merged


def _display_name(preset_id: str, preset: dict) -> str:
    """
    Строка, которая будет показана в ComboBox.
    Сам «бейдж» рисуется делегатом; здесь ‑ лишь имя.
    """
    return preset.get("name", preset_id)


# ──────────────────────────────────────────────────────────
#                КАСТОМНЫЙ  DELEGATE  ДЛЯ БЕЙДЖЕЙ
# ──────────────────────────────────────────────────────────
class _ProviderDelegate(QStyledItemDelegate):
    """
    Рисует слева от текста:
        free   -> [FREE]
        paid   -> $
        mixed  -> [FREE] / $
    """

    _free_pm:   QPixmap | None = None   # кеш «FREE»

    @classmethod
    def _free_pixmap(cls):
        if cls._free_pm is None:
            font = QFont("Segoe UI", 7, QFont.Weight.Bold)
            metrics = QFontMetrics(font)
            text_w  = metrics.horizontalAdvance("FREE")
            w, h = text_w + 8, 14              # 4 px слева + 4 px справа
            pm = QPixmap(w, h)
            pm.fill(Qt.GlobalColor.transparent)

            p = QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor("#ffffff")); p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, w, h, 3, 3)

            p.setPen(QColor("#102035")); p.setFont(font)
            p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "FREE")
            p.end()

            cls._free_pm = pm
        return cls._free_pm

    # -----------------------------------------------------
    def __init__(self, mixed_presets: dict, display2id: dict, parent=None):
        super().__init__(parent)
        self._mp  = mixed_presets
        self._d2i = display2id

    

    # -----------------------------------------------------
    def paint(self, painter, option, index):
        # Фон + выделение
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        text = index.data()
        pid  = self._d2i.get(text, "")
        pricing = self._mp.get(pid, {}).get("pricing", "")

        dollar_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        ascent      = QFontMetrics(dollar_font).ascent()   # высота над базовой

        x = option.rect.x() + 4
        y = option.rect.y() + (option.rect.height() - 16) // 2

        # --- бейдж / значки ---
        if pricing == "free":
            painter.drawPixmap(x, y, self._free_pixmap())
            x += self._free_pixmap().width() + 6

        elif pricing == "paid":
            painter.setPen(QColor("#2ecc71"))
            painter.setFont(dollar_font)
            dollar_w = QFontMetrics(dollar_font).horizontalAdvance("💲")
            baseline = y + ascent        # ← базовая линия
            painter.drawText(x, baseline, "💲")
            x += dollar_w + 6

        elif pricing == "mixed":
            painter.drawPixmap(x, y, self._free_pixmap())
            x += self._free_pixmap().width() + 4

            painter.setPen(QColor("#ffffff"))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(x, y + ascent - 1, "/")
            x += 3

            painter.setPen(QColor("#2ecc71"))
            painter.setFont(dollar_font)
            dollar_w = QFontMetrics(dollar_font).horizontalAdvance("💲")
            baseline = y + ascent
            painter.drawText(x, baseline, "💲")
            x += dollar_w + 6

        # --- текст провайдера ---
        painter.setPen(option.palette.color(
            QPalette.ColorRole.HighlightedText
            if option.state & QStyle.StateFlag.State_Selected
            else QPalette.ColorRole.Text))
        painter.setFont(option.font)
        txt_rect = option.rect.adjusted(x - option.rect.x(), 0, -4, 0)
        painter.drawText(txt_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    def sizeHint(self, option, index):
        sz = super().sizeHint(option, index)
        return sz.expandedTo(QSize(140, 20))


# ──────────────────────────────────────────────────────────
#               ГЛАВНАЯ ФУНКЦИЯ  ДЛЯ  UI
# ──────────────────────────────────────────────────────────
def setup_api_controls(self, parent):
    """
    Создаёт секцию «API settings»; всё, что было у вас – сохранено,
    добавляется только делегат для красивых бейджей.
    """
    # ── данные из settings ─────────────────────────────────
    provider_data   = self.settings.get("API_PROVIDER_DATA", {})
    custom_presets  = self.settings.get("CUSTOM_API_PRESETS", {})
    MIXED_PRESETS   = _mixed_presets(API_PRESETS, custom_presets)

    # ── URL builder ───────────────────────────────────────
    def build_dynamic_url(pid: str, model: str, key: str) -> str:
        pre = MIXED_PRESETS.get(pid, {})
        if not pre:
            return ""
        url_tpl = pre.get("url_tpl") or pre.get("url", "")
        url     = url_tpl.format(model=model) if "{model}" in url_tpl else url_tpl
        if pre.get("add_key") and key:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}key={key}"
        return url

    # ── state helpers ─────────────────────────────────────
    def save_provider_state(pid: str):
        if not pid:
            return
        provider_data[pid] = {
            "NM_API_URL":   api_url_entry.text().strip(),
            "NM_API_MODEL": api_model_entry.text().strip(),
            "NM_API_KEY":   api_key_entry.text().strip(),
            "NM_API_KEY_RES": self.settings.get("NM_API_KEY_RES", ""),
            "NM_API_REQ":   nm_api_req_checkbox.isChecked(),
            "GEMINI_CASE":  gemini_case_checkbox.isChecked(),
        }
        self.settings.set("API_PROVIDER_DATA", provider_data)
        self.settings.save_settings()

    def load_provider_state(pid: str, fallback: bool = True):
        stored = provider_data.get(pid)
        if stored:
            api_url_entry.setText(stored.get("NM_API_URL", ""))
            api_model_entry.setText(stored.get("NM_API_MODEL", ""))
            api_key_entry.setText(stored.get("NM_API_KEY", ""))

            nm_api_req_checkbox.setChecked(stored.get("NM_API_REQ", False))
            gemini_case_checkbox.setChecked(stored.get("GEMINI_CASE", False))

            self._save_setting("NM_API_URL",   stored.get("NM_API_URL", ""))
            self._save_setting("NM_API_MODEL", stored.get("NM_API_MODEL", ""))
            self._save_setting("NM_API_KEY",   stored.get("NM_API_KEY", ""))
            self._save_setting("NM_API_REQ",   stored.get("NM_API_REQ", False))
            self._save_setting("GEMINI_CASE",  stored.get("GEMINI_CASE", False))
            self._save_setting("NM_API_KEY_RES", stored.get("NM_API_KEY_RES", ""))
        elif fallback:
            api_key_entry.setText("")
            self._save_setting("NM_API_KEY", "")
            apply_preset(pid)

    # ── Combo helpers ─────────────────────────────────────
    DISPLAY2ID = {}
    ID2DISPLAY = {}

    def combo_current_id() -> str:
        return DISPLAY2ID.get(api_provider_combo.currentText(), "custom")

    # ── список провайдеров ────────────────────────────────
    builtin_pairs = [(pid, _display_name(pid, API_PRESETS[pid]))
                     for pid in API_PRESETS]
    builtin_pairs.append(("custom", "Custom"))
    custom_pairs    = [(pid, pid) for pid in custom_presets]
    provider_pairs  = builtin_pairs + custom_pairs
    separator_index = len(builtin_pairs)

    for pid, text in provider_pairs:
        DISPLAY2ID[text] = pid
        ID2DISPLAY[pid]  = text

    # ── FORM CONFIG  (НЕ трогаем) ─────────────────────────
    config = [
        {'label': _('Провайдер', 'Provider'),
         'key': 'API_PROVIDER', 'type': 'combobox',
         'options': [p[1] for p in provider_pairs],
         'default': 'Custom', 'widget_name': 'api_provider_combo'},
        {'type': 'button_group',
         'buttons': [
             {'label': _('Сохранить / обновить пресет', 'Save / update preset'),
              'command': lambda: _btn_save_preset()},
             {'label': _('Удалить пресет', 'Delete preset'),
              'command': lambda: _btn_delete_preset()},
         ]},
        {'label': _('Ссылка', 'URL'),
         'key': 'NM_API_URL', 'type': 'entry', 'widget_name': 'api_url_entry'},
        {'label': _('Модель', 'Model'),
         'key': 'NM_API_MODEL', 'type': 'entry', 'widget_name': 'api_model_entry'},
        {'label': _('Ключ', 'Key'),
         'key': 'NM_API_KEY',
         'type': 'entry',
         'widget_name': 'api_key_entry',
         'hide': True},
        {'label': _('Через Request', 'Using Request'),
         'key': 'NM_API_REQ', 'type': 'checkbutton',
         'widget_name': 'nm_api_req_checkbox'},
        {'label': _('Структура Гемини', 'Gemini Structure'),
         'key': 'GEMINI_CASE', 'type': 'checkbutton',
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
    self.create_settings_section(parent, _("Настройки API", "API settings"), config)

    # ── ссылки на виджеты ────────────────────────────────
    api_provider_combo: QComboBox = getattr(self, 'api_provider_combo')
    api_model_entry   = getattr(self, 'api_model_entry')
    api_url_entry     = getattr(self, 'api_url_entry')
    api_key_entry     = getattr(self, 'api_key_entry')
    gemini_case_checkbox = getattr(self, 'gemini_case_checkbox')
    nm_api_req_checkbox  = getattr(self, 'nm_api_req_checkbox')

    # ── разделитель ───────────────────────────────────────
    api_provider_combo.insertSeparator(separator_index)

    # ── ПОДКЛЮЧАЕМ delegate (после QApplication) ──────────
    api_provider_combo.view().setItemDelegate(
        _ProviderDelegate(MIXED_PRESETS, DISPLAY2ID, api_provider_combo)
    )

    # ── URL updater ───────────────────────────────────────
    def update_url(force: bool = False):
        pid = combo_current_id()
        if pid == "custom" and not force:
            return
        url = build_dynamic_url(pid,
                                api_model_entry.text().strip(),
                                api_key_entry.text().strip())
        api_url_entry.setText(url)
        self._save_setting("NM_API_URL", url)
        save_provider_state(pid)

    # ── preset apply ──────────────────────────────────────
    def apply_preset(pid: str):
        pre = MIXED_PRESETS.get(pid)
        if not pre:
            return
        api_model_entry.setText(pre.get("model", ""))
        api_key_entry.setText("")
        nm_api_req_checkbox.setChecked(pre.get("nm_api_req", False))
        gemini_case_checkbox.setChecked(pre.get("gemini_case", False))

        self._save_setting("NM_API_MODEL",  pre.get("model", ""))
        self._save_setting("NM_API_KEY",    "")
        self._save_setting("NM_API_REQ",    pre.get("nm_api_req", False))
        self._save_setting("GEMINI_CASE",   pre.get("gemini_case", False))
        update_url(force=True)

    # ── provider change ───────────────────────────────────
    self._last_provider = combo_current_id()
    def on_provider_changed():
        save_provider_state(self._last_provider)
        new_id = combo_current_id()
        load_provider_state(new_id, fallback=True)
        self._last_provider = new_id
        update_url(force=True)
    api_provider_combo.currentIndexChanged.connect(lambda _: on_provider_changed())

    # ── live URL updates ──────────────────────────────────
    api_model_entry.textChanged.connect(lambda _: update_url())
    api_key_entry.textChanged.connect(lambda _: update_url())

    # ── начальное восстановление ──────────────────────────
    QTimer.singleShot(0, lambda: load_provider_state(combo_current_id(), fallback=False))
    QTimer.singleShot(0, lambda: update_url(force=True))

    # ──────────────────────────────────────────────────────
    #                  SAVE / DELETE  (custom)
    # ──────────────────────────────────────────────────────
    def _btn_save_preset():
        from PyQt6.QtWidgets import QInputDialog
        cur_id = combo_current_id()

        if cur_id in API_PRESETS or cur_id == "custom":
            name, ok = QInputDialog.getText(
                self, _("Имя пресета", "Preset name"),
                _("Название нового пресета:", "New preset name:"))
            if not ok or not name.strip():
                return
            pid = name.strip()
        else:
            pid = cur_id

        if pid in API_PRESETS:
            QMessageBox.warning(self, _("Конфликт", "Conflict"),
                                _("ID зарезервирован встроенным пресетом",
                                  "This ID is reserved for builtin preset"))
            return

        custom_presets[pid] = {
            "url":   api_url_entry.text().strip(),
            "model": api_model_entry.text().strip(),
            "pricing": "mixed"
        }
        self.settings.set("CUSTOM_API_PRESETS", custom_presets)
        self.settings.save_settings()
        MIXED_PRESETS[pid] = custom_presets[pid]

        if pid not in [p[0] for p in provider_pairs]:
            provider_pairs.append((pid, pid))
            DISPLAY2ID[pid] = pid; ID2DISPLAY[pid] = pid
            api_provider_combo.addItem(pid)

        api_provider_combo.setCurrentText(ID2DISPLAY[pid])
        save_provider_state(pid)

    def _btn_delete_preset():
        cur_id = combo_current_id()
        if cur_id in custom_presets:
            if QMessageBox.question(
                    self, _("Удалить", "Delete"),
                    _("Удалить пресет «{}»?".format(cur_id),
                      "Delete preset «{}»?".format(cur_id)),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            ) != QMessageBox.StandardButton.Yes:
                return

            custom_presets.pop(cur_id, None)
            provider_data.pop(cur_id, None)
            self.settings.set("CUSTOM_API_PRESETS", custom_presets)
            self.settings.set("API_PROVIDER_DATA", provider_data)
            self.settings.save_settings()

            idx = api_provider_combo.findText(ID2DISPLAY[cur_id])
            if idx >= 0:
                api_provider_combo.removeItem(idx)
            api_provider_combo.setCurrentText('Custom')