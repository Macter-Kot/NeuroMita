import re
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QSizePolicy, QLineEdit, QCheckBox
)

from utils import getTranslationVariant as _
from main_logger import logger
from core.events import get_event_bus, Events
from styles.main_styles import get_theme
from .ui import make_row


def wire_microphone_settings_logic(self):
    """
    Подключает всю логику к уже построенному UI.
    self — это ваш MainView (или аналог).
    """
    bus = get_event_bus()
    theme = get_theme()

    # --- Вспомогательная "пилюля" (через сигнал главного окна)
    def set_pill_called(lbl: QLabel, text: str, kind: str = "info"):
        self.asr_set_pill.emit({
            "label": lbl,
            "text": text,
            "kind": kind
        })

    def set_pill(data):
        lbl: QLabel = data["label"]
        text: str = data["text"]
        kind: str = data["kind"]

        if kind == "ok":
            fg = theme["success"]
            bg = "rgba(61,166,110,0.12)"
            br = "rgba(61,166,110,0.45)"
        elif kind == "warn":
            fg = theme["danger"]
            bg = "rgba(214,69,69,0.12)"
            br = "rgba(214,69,69,0.45)"
        elif kind == "progress":
            fg = theme["accent"]
            bg = "rgba(138,43,226,0.12)"
            br = theme["accent_border"]
        else:
            fg = theme["text"]
            bg = theme["chip_bg"]
            br = theme["border_soft"]

        lbl.setText(text)
        lbl.setStyleSheet(
            f"QLabel {{ padding: 2px 6px; border-radius: 8px; "
            f"font-weight: 600; font-size: 11px; color: {fg}; background: {bg}; border: 1px solid {br}; }}"
        )

    self.asr_set_pill.connect(set_pill)
    set_pill_called(self.asr_status_label, "—", "info")
    set_pill_called(self.asr_init_status, "—", "info")

    # --- Хелперы
    def truncate_text_for_width(text, widget, max_width):
        """Обрезает текст чтобы он помещался в заданную ширину с учетом '...' """
        metrics = QFontMetrics(widget.font())
        ellipsis = "..."
        ellipsis_width = metrics.horizontalAdvance(ellipsis)
        available_width = max(max_width - ellipsis_width - 20, 20)

        if metrics.horizontalAdvance(text) <= available_width:
            return text

        left, right = 0, len(text)
        result = ""
        while left <= right:
            mid = (left + right) // 2
            truncated = text[:mid]
            if metrics.horizontalAdvance(truncated) <= available_width:
                result = truncated
                left = mid + 1
            else:
                right = mid - 1

        return result + ellipsis if result else ellipsis

    # --- Микрофоны
    def populate_mics():
        res = bus.emit_and_wait(Events.Speech.GET_MICROPHONE_LIST, timeout=1.0)
        mic_list = res[0] if res else [_("Микрофоны не найдены", "No microphones found")]

        self.mic_combobox.blockSignals(True)
        try:
            self.mic_combobox.clear()
            max_text_width = self.mic_combobox.maximumWidth() if self.mic_combobox.maximumWidth() < 10000 else 180

            for mic_name in mic_list:
                display = truncate_text_for_width(mic_name, self.mic_combobox, max_text_width)
                if len(display) > 30:
                    display = mic_name[:27] + "..."

                self.mic_combobox.addItem(display)
                idx = self.mic_combobox.count() - 1
                self.mic_combobox.setItemData(idx, mic_name, Qt.ItemDataRole.UserRole)
                self.mic_combobox.setItemData(idx, mic_name, Qt.ItemDataRole.ToolTipRole)

            current_full = self.settings.get('MIC_DEVICE', mic_list[0] if mic_list else "")
            for i in range(self.mic_combobox.count()):
                if self.mic_combobox.itemData(i, Qt.ItemDataRole.UserRole) == current_full:
                    self.mic_combobox.setCurrentIndex(i)
                    break
            self.mic_combobox.setToolTip(current_full)
        finally:
            self.mic_combobox.blockSignals(False)

    def on_mic_changed(index):
        if index < 0:
            return
        full_name = self.mic_combobox.itemData(index, Qt.ItemDataRole.UserRole)
        self._save_setting('MIC_DEVICE', full_name)
        self.mic_combobox.setToolTip(full_name)
        on_mic_selected(self, full_name)

    self.mic_combobox.currentIndexChanged.connect(on_mic_changed)
    self.mic_refresh_button.clicked.connect(populate_mics)

    # --- Движок распознавания
    def clear_layout(lay: QVBoxLayout):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def rebuild_model_settings(engine: str):
        clear_layout(self.model_settings_layout)

        schema_res = bus.emit_and_wait(Events.Speech.GET_RECOGNIZER_SETTINGS_SCHEMA, {'engine': engine}, timeout=1.0)
        schema = schema_res[0] if schema_res else []

        vals_res = bus.emit_and_wait(Events.Speech.GET_RECOGNIZER_SETTINGS, {'engine': engine}, timeout=1.0)
        values = vals_res[0] if vals_res else {}

        for field in schema:
            key = field.get("key")
            label_ru = field.get("label_ru", key)
            label_en = field.get("label_en", key)
            label_txt = _(label_ru, label_en)
            ftype = field.get("type", "entry")

            field_widget = QWidget()
            fw_h = QHBoxLayout(field_widget)
            fw_h.setContentsMargins(0, 0, 0, 0)
            fw_h.setSpacing(6)

            if ftype == "combobox":
                cb = QComboBox()
                cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                cb.setMaximumWidth(150)
                for opt in field.get("options", []):
                    cb.addItem(str(opt))
                current = str(values.get(key, field.get("default", "")))
                if current:
                    idx = cb.findText(current, Qt.MatchFlag.MatchFixedString)
                    if idx >= 0:
                        cb.setCurrentIndex(idx)
                    else:
                        cb.setCurrentText(current)
                cb.currentTextChanged.connect(
                    lambda v, e=engine, k=key: bus.emit(
                        Events.Speech.SET_RECOGNIZER_OPTION, {'engine': e, 'key': k, 'value': v}
                    )
                )
                fw_h.addWidget(cb, 1)

            elif ftype == "check":
                chk = QCheckBox("")
                chk.setChecked(bool(values.get(key, field.get("default", False))))
                chk.toggled.connect(
                    lambda state, e=engine, k=key: bus.emit(
                        Events.Speech.SET_RECOGNIZER_OPTION, {'engine': e, 'key': k, 'value': bool(state)}
                    )
                )
                fw_h.addWidget(chk, 0, Qt.AlignmentFlag.AlignLeft)

            else:
                edit = QLineEdit()
                edit.setText(str(values.get(key, field.get("default", ""))))
                edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

                def on_edit_finished(e=engine, k=key, w=edit):
                    bus.emit(Events.Speech.SET_RECOGNIZER_OPTION, {'engine': e, 'key': k, 'value': w.text().strip()})

                edit.editingFinished.connect(on_edit_finished)
                fw_h.addWidget(edit, 1)

            self.model_settings_layout.addWidget(make_row(label_txt, field_widget, self.mic_label_width))

    def _default_install_text():
        return _("Установить модель распознавания", "Install ASR model")

    def apply_asr_install_status(engine: str):
        """
        Единая логика статуса: для любого движка показываем Installed/Not installed.
        Если не установлен — показываем полноширинную кнопку установки и блокируем
        чекбокс активности микрофона.
        """
        res = bus.emit_and_wait(Events.Speech.CHECK_ASR_MODEL_INSTALLED, {'model': engine}, timeout=1.0)
        installed = bool(res and res[0])

        # Сброс подписи под кнопкой
        self.install_status_label.setText("")
        self.install_status_label.setVisible(False)

        # Восстановим внешний вид кнопки, текст и enable (на всякий случай)
        self.install_model_button.setEnabled(True)
        self.install_model_button.setText(_default_install_text())
        if hasattr(self, "_install_btn_default_style"):
            self.install_model_button.setStyleSheet(self._install_btn_default_style)
        else:
            self._install_btn_default_style = self.install_model_button.styleSheet()

        if installed:
            set_pill_called(self.asr_status_label, _('Установлено', 'Installed'), "ok")
            self.install_model_button.setVisible(False)
            self.mic_active_checkbox.setEnabled(True)
        else:
            set_pill_called(self.asr_status_label, _('Не установлено', 'Not installed'), "warn")
            self.install_model_button.setVisible(True)
            self.mic_active_checkbox.setChecked(False)
            self._save_setting('MIC_ACTIVE', False)
            self.mic_active_checkbox.setEnabled(False)

    def start_install():
        engine = self.recognizer_combobox.currentText()
        # Сохраним исходный стиль, если ещё не
        if not hasattr(self, "_install_btn_default_style"):
            self._install_btn_default_style = self.install_model_button.styleSheet()

        # Визуально "блокируем" кнопку и меняем текст
        self.install_model_button.setEnabled(False)
        self.install_model_button.setText(_("Установка...", "Installing..."))
        self.install_model_button.setStyleSheet("""
            QPushButton {
                background-color: #7f8c8d;
                color: #ecf0f1;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
        """)

        set_pill_called(self.asr_status_label, _('Установка...', 'Installing...'), "progress")
        self.install_status_label.setVisible(True)
        self.install_status_label.setText(_("Подготовка...", "Preparing..."))
        subs = []

        def cleanup():
            for name, cb in subs:
                bus.unsubscribe(name, cb)
            subs.clear()
            # Включать кнопку назад не обязательно — apply_asr_install_status сам решит видимость,
            # но если видна, вернём стиль и текст.
            self.install_model_button.setEnabled(True)
            self.install_model_button.setText(_default_install_text())
            if hasattr(self, "_install_btn_default_style"):
                self.install_model_button.setStyleSheet(self._install_btn_default_style)
            self.install_status_label.setVisible(False)

        def on_progress(event):
            if event.data.get('model') == engine:
                pr = event.data.get('progress', 0)
                self.install_status_label.setText(f"{pr}%")

        def on_finished(event):
            if event.data.get('model') == engine:
                self.install_status_label.setText(_("Готово", "Done"))
                cleanup()
                apply_asr_install_status(engine)

        def on_failed(event):
            if event.data.get('model') == engine:
                self.install_status_label.setText(_("Ошибка", "Error"))
                set_pill_called(self.asr_status_label, _('Ошибка', 'Error'), "warn")
                cleanup()
                apply_asr_install_status(engine)

        subs.extend([
            (Events.Speech.ASR_MODEL_INSTALL_PROGRESS, on_progress),
            (Events.Speech.ASR_MODEL_INSTALL_FINISHED, on_finished),
            (Events.Speech.ASR_MODEL_INSTALL_FAILED, on_failed),
        ])
        for n, cb in subs:
            bus.subscribe(n, cb, weak=False)

        bus.emit(Events.Speech.INSTALL_ASR_MODEL, {'model': engine})

    self.install_model_button.clicked.connect(start_install)

    def set_engine(engine: str):
        # Сохраняем, перестраиваем и обновляем статус именно выбранного движка
        self._save_setting('RECOGNIZER_TYPE', engine)
        rebuild_model_settings(engine)
        apply_asr_install_status(engine)

    self.recognizer_combobox.currentTextChanged.connect(set_engine)

    # Переключатели
    def on_active_toggled(state: int):
        self._save_setting('MIC_ACTIVE', bool(state))

    def on_instant_toggled(state: int):
        self._save_setting('MIC_INSTANT_SENT', bool(state))

    self.mic_active_checkbox.stateChanged.connect(on_active_toggled)
    self.mic_instant_checkbox.stateChanged.connect(on_instant_toggled)

    # События инициализации (начало/готово)
    def on_asr_init_started(_event):
        set_pill_called(self.asr_init_status, _("Инициализация...", "Initializing..."), "progress")

    def on_asr_initialized(_event):
        set_pill_called(self.asr_init_status, _("Готово", "Ready"), "ok")

    bus.subscribe(Events.Speech.ASR_MODEL_INIT_STARTED, on_asr_init_started, weak=False)
    bus.subscribe(Events.Speech.ASR_MODEL_INITIALIZED, on_asr_initialized, weak=False)

    # Инициализация UI
    def refresh_engine_ui():
        eng = self.recognizer_combobox.currentText()
        rebuild_model_settings(eng)
        apply_asr_install_status(eng)

    populate_mics()
    refresh_engine_ui()
    QTimer.singleShot(400, refresh_engine_ui)


def on_mic_selected(gui, full_device_name=None):
    """
    Устанавливает микрофон по строке вида "Name (ID)".
    Исправлен разбор ID (корректный regex).
    """
    if not hasattr(gui, 'mic_combobox'):
        return
    bus = get_event_bus()

    if full_device_name is None:
        idx = gui.mic_combobox.currentIndex()
        if idx >= 0:
            full_device_name = gui.mic_combobox.itemData(idx, Qt.ItemDataRole.UserRole)

    selection = full_device_name or ""
    if selection and '(' in selection:
        try:
            microphone_name = selection.rsplit(" (", 1)[0]
            m = re.search(r'KATEX_INLINE_OPEN(\d+)KATEX_INLINE_CLOSE\s*$', selection)
            if m:
                device_id = int(m.group(1))
                bus.emit(Events.Speech.SET_MICROPHONE, {'name': microphone_name, 'device_id': device_id})
                if gui.settings.get("MIC_ACTIVE", False):
                    bus.emit(Events.Speech.RESTART_SPEECH_RECOGNITION, {'device_id': device_id})
        except Exception as e:
            logger.error(f"Ошибка выбора микрофона: {e}")


def load_mic_settings(gui):
    """
    Совместимость: выставляет сохранённый микрофон и активность.
    """
    try:
        bus = get_event_bus()
        device_id = gui.settings.get("NM_MICROPHONE_ID", 0)
        device_name = gui.settings.get("NM_MICROPHONE_NAME", "")
        full = f"{device_name} ({device_id})"

        if hasattr(gui, 'mic_combobox'):
            found = False
            for i in range(gui.mic_combobox.count()):
                if gui.mic_combobox.itemData(i, Qt.ItemDataRole.UserRole) == full:
                    gui.mic_combobox.setCurrentIndex(i)
                    gui.mic_combobox.setToolTip(full)
                    found = True
                    break
            if not found and gui.mic_combobox.count() > 0:
                gui.mic_combobox.setCurrentIndex(0)
                gui.mic_combobox.setToolTip(gui.mic_combobox.itemData(0, Qt.ItemDataRole.UserRole))

        bus.emit(Events.Speech.SET_MICROPHONE, {'name': device_name, 'device_id': device_id})

        if gui.settings.get("MIC_ACTIVE", False) and hasattr(gui, 'mic_active_checkbox'):
            gui.mic_active_checkbox.setChecked(True)

    except Exception as e:
        logger.error(f"Ошибка загрузки настроек микрофона: {e}")