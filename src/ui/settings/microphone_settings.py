# File: src/ui/settings/microphone_settings.py

import re
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QComboBox,
    QPushButton, QSizePolicy, QFrame, QLineEdit, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFontMetrics
import qtawesome as qta

from ui.gui_templates import create_section_header
from utils import getTranslationVariant as _
from main_logger import logger
from core.events import get_event_bus, Events
from styles.main_styles import get_theme


def setup_microphone_controls(gui, parent_layout):
    create_section_header(parent_layout, _("Настройки микрофона", "Microphone Settings"))
    bus = get_event_bus()
    theme = get_theme()

    # Уменьшенная ширина колонки лейблов для лучшего вмещения в панель
    overlay_w = getattr(gui, "SETTINGS_PANEL_WIDTH", 400)
    label_w = max(90, min(120, int(overlay_w * 0.3)))  # Уменьшено с 110-160 до 90-120

    def make_row(label_text: str, field_widget: QWidget) -> QWidget:
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)  # Уменьшено с 8 до 6

        lbl = QLabel(label_text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        lbl.setFixedWidth(label_w)
        hl.addWidget(lbl, 0)

        hl.addWidget(field_widget, 1)
        return row

    def set_pill_called(lbl: QLabel, text: str, kind: str = "info"):
        gui.asr_set_pill.emit({
            "label": lbl,
            "text": text,
            "kind": kind
        })

    def set_pill(data):
        lbl: QLabel = data["label"]
        text: str = data["text"]
        kind: str = data["kind"]

        # info | ok | warn | progress
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
            f"QLabel {{ padding: 2px 6px; border-radius: 8px; "  # Уменьшен padding с 8px до 6px
            f"font-weight: 600; font-size: 11px; color: {fg}; background: {bg}; border: 1px solid {br}; }}"
        )

    gui.asr_set_pill.connect(set_pill)

    # Корневой контейнер секции
    root = QWidget()
    root_lay = QVBoxLayout(root)
    root_lay.setContentsMargins(0, 0, 0, 0)
    root_lay.setSpacing(6)  # Уменьшено с 8 до 6

    # ----- Строка: Тип распознавания + статус + установка
    engine_field = QWidget()
    eng_h = QHBoxLayout(engine_field)
    eng_h.setContentsMargins(0, 0, 0, 0)
    eng_h.setSpacing(6)  # Уменьшено с 8 до 6

    gui.recognizer_combobox = QComboBox()
    gui.recognizer_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    gui.recognizer_combobox.addItems(["google", "gigaam"])
    gui.recognizer_combobox.setCurrentText(gui.settings.get('RECOGNIZER_TYPE', 'google'))
    gui.recognizer_combobox.setToolTip(_("Выберите движок распознавания речи", "Select speech recognition engine"))
    eng_h.addWidget(gui.recognizer_combobox, 1)

    # Статусная пилюля (Installed / Not installed / Ready / Installing...)
    gui.asr_status_label = QLabel("—")
    set_pill_called(gui.asr_status_label, "—", "info")
    eng_h.addWidget(gui.asr_status_label, 0, Qt.AlignmentFlag.AlignVCenter)

    # Кнопка установки (ограничим ширину еще больше)
    gui.install_model_button = QPushButton(_("Установить", "Install"))
    gui.install_model_button.setObjectName("SecondaryButton")
    gui.install_model_button.setIcon(qta.icon('fa5s.download', color='#ffffff'))
    gui.install_model_button.setVisible(False)
    gui.install_model_button.setMaximumWidth(100)  # Уменьшено с 150 до 100
    gui.install_model_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    eng_h.addWidget(gui.install_model_button, 0)

    # Компактная строка прогресса установки (скрыта по умолчанию)
    gui.install_status_label = QLabel("")
    gui.install_status_label.setStyleSheet(f"color: {theme['muted']}; font-size: 10px;")  # Уменьшен шрифт
    gui.install_status_label.setVisible(False)  # Скрываем когда не используется
    eng_h.addWidget(gui.install_status_label, 0, Qt.AlignmentFlag.AlignVCenter)

    root_lay.addWidget(make_row(_("Распознавание", "Recognition"), engine_field))

    # ----- Строка: Микрофон + кнопка "Обновить" (иконка, фикс. размер)
    mic_field = QWidget()
    mic_h = QHBoxLayout(mic_field)
    mic_h.setContentsMargins(0, 0, 0, 0)
    mic_h.setSpacing(6)  # Уменьшено с 8 до 6

    gui.mic_combobox = QComboBox()
    gui.mic_combobox.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    # ВАЖНО: Ограничиваем максимальную ширину комбобокса
    gui.mic_combobox.setMaximumWidth(200)  # Фиксированная максимальная ширина
    gui.mic_combobox.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
    mic_h.addWidget(gui.mic_combobox, 1)

    btn_refresh = QPushButton()
    btn_refresh.setObjectName("SecondaryButton")
    btn_refresh.setIcon(qta.icon('fa5s.sync', color='#ffffff'))
    btn_refresh.setToolTip(_("Обновить список микрофонов", "Refresh microphone list"))
    btn_refresh.setFixedSize(28, 26)  # Еще более компактно
    mic_h.addWidget(btn_refresh, 0)

    root_lay.addWidget(make_row(_("Микрофон", "Microphone"), mic_field))

    # ----- Строка: Переключатели (горизонтально для экономии места)
    toggles_field = QWidget()
    toggles_h = QHBoxLayout(toggles_field)  # Изменено на горизонтальный layout
    toggles_h.setContentsMargins(0, 0, 0, 0)
    toggles_h.setSpacing(10)

    gui.mic_active_checkbox = QCheckBox(_("Вкл", "On"))  # Сокращенный текст
    gui.mic_active_checkbox.setChecked(bool(gui.settings.get("MIC_ACTIVE")))
    toggles_h.addWidget(gui.mic_active_checkbox, 0)

    gui.mic_instant_checkbox = QCheckBox(_("Мгновенно", "Instant"))  # Сокращенный текст
    gui.mic_instant_checkbox.setChecked(bool(gui.settings.get("MIC_INSTANT_SENT")))
    gui.mic_instant_checkbox.setToolTip(_("Мгновенная отправка распознанного текста", "Send recognized text immediately"))
    toggles_h.addWidget(gui.mic_instant_checkbox, 0)
    
    toggles_h.addStretch()

    root_lay.addWidget(make_row(_("Опции", "Options"), toggles_field))

    # ----- Строка: Статус инициализации (пилюля)
    gui.asr_init_status = QLabel("—")
    set_pill_called(gui.asr_init_status, "—", "info")
    root_lay.addWidget(make_row(_("Статус", "Status"), gui.asr_init_status))

    # ----- Динамические опции движка (как раньше, но с тем же выравниванием)
    gui.model_settings_frame = QFrame()
    gui.model_settings_layout = QVBoxLayout(gui.model_settings_frame)
    gui.model_settings_layout.setContentsMargins(0, 0, 0, 0)
    gui.model_settings_layout.setSpacing(4)  # Уменьшено с 6 до 4
    root_lay.addWidget(gui.model_settings_frame)

    parent_layout.addWidget(root)
    parent_layout.addStretch()

    # ===== Логика =====
    def truncate_text_for_width(text, widget, max_width):
        """Обрезает текст чтобы он помещался в заданную ширину с учетом '...' """
        metrics = QFontMetrics(widget.font())
        ellipsis = "..."
        ellipsis_width = metrics.horizontalAdvance(ellipsis)
        available_width = max_width - ellipsis_width - 20  # Оставляем немного места для padding
        
        if metrics.horizontalAdvance(text) <= available_width:
            return text
            
        # Бинарный поиск оптимальной длины
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

    def populate_mics():
        res = bus.emit_and_wait(Events.Speech.GET_MICROPHONE_LIST, timeout=1.0)
        mic_list = res[0] if res else [_("Микрофоны не найдены", "No microphones found")]

        gui.mic_combobox.blockSignals(True)
        try:
            gui.mic_combobox.clear()
            
            # Получаем максимальную доступную ширину для текста в комбобоксе
            max_text_width = gui.mic_combobox.maximumWidth() if gui.mic_combobox.maximumWidth() < 10000 else 180
            
            for mic_name in mic_list:
                # Обрезаем отображаемое имя для комбобокса
                display = truncate_text_for_width(mic_name, gui.mic_combobox, max_text_width)
                
                # Дополнительная защита - если все еще слишком длинно, обрезаем по символам
                if len(display) > 30:  # Максимум 30 символов
                    display = mic_name[:27] + "..."
                    
                gui.mic_combobox.addItem(display)
                idx = gui.mic_combobox.count() - 1
                # Сохраняем полное имя в UserRole для последующего использования
                gui.mic_combobox.setItemData(idx, mic_name, Qt.ItemDataRole.UserRole)
                # Полное имя в tooltip
                gui.mic_combobox.setItemData(idx, mic_name, Qt.ItemDataRole.ToolTipRole)
                
            current_full = gui.settings.get('MIC_DEVICE', mic_list[0] if mic_list else "")
            for i in range(gui.mic_combobox.count()):
                if gui.mic_combobox.itemData(i, Qt.ItemDataRole.UserRole) == current_full:
                    gui.mic_combobox.setCurrentIndex(i)
                    break
            gui.mic_combobox.setToolTip(current_full)
        finally:
            gui.mic_combobox.blockSignals(False)

    def on_mic_changed(index):
        if index < 0:
            return
        full_name = gui.mic_combobox.itemData(index, Qt.ItemDataRole.UserRole)
        gui._save_setting('MIC_DEVICE', full_name)
        gui.mic_combobox.setToolTip(full_name)
        on_mic_selected(gui, full_name)

    gui.mic_combobox.currentIndexChanged.connect(on_mic_changed)
    btn_refresh.clicked.connect(populate_mics)

    # Смена движка
    def set_engine(engine: str):
        gui._save_setting('RECOGNIZER_TYPE', engine)
        rebuild_model_settings(engine)
        apply_asr_install_status(engine)

    gui.recognizer_combobox.currentTextChanged.connect(set_engine)

    # Построение динамических опций (с тем же двухколоночным видом)
    def clear_layout(lay: QVBoxLayout):
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def rebuild_model_settings(engine: str):
        clear_layout(gui.model_settings_layout)

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
            fw_h.setSpacing(6)  # Уменьшено с 8 до 6

            if ftype == "combobox":
                cb = QComboBox()
                cb.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                # Ограничиваем ширину динамических комбобоксов тоже
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

            gui.model_settings_layout.addWidget(make_row(label_txt, field_widget))

    # Установка/проверка статусов
    def apply_asr_install_status(engine: str):
        res = bus.emit_and_wait(Events.Speech.CHECK_ASR_MODEL_INSTALLED, {'model': engine}, timeout=1.0)
        installed = bool(res and res[0])

        gui.install_status_label.setText("")
        gui.install_status_label.setVisible(False)  # Скрываем когда не используется

        if engine == "google":
            set_pill_called(gui.asr_status_label, _('Готово', 'Ready'), "ok")
            gui.install_model_button.setVisible(False)
            gui.mic_active_checkbox.setEnabled(True)
        else:
            if installed:
                set_pill_called(gui.asr_status_label, _('Установлено', 'Installed'), "ok")
                gui.install_model_button.setVisible(False)
                gui.mic_active_checkbox.setEnabled(True)
            else:
                set_pill_called(gui.asr_status_label, _('Не установлено', 'Not installed'), "warn")
                gui.install_model_button.setVisible(True)
                gui.mic_active_checkbox.setChecked(False)
                gui._save_setting('MIC_ACTIVE', False)
                gui.mic_active_checkbox.setEnabled(False)

    # Старт установки модели (кнопка и компактная строка статуса справа)
    def start_install():
        engine = gui.recognizer_combobox.currentText()
        gui.install_model_button.setEnabled(False)
        set_pill_called(gui.asr_status_label, _('Установка...', 'Installing...'), "progress")
        gui.install_status_label.setVisible(True)  # Показываем при установке
        gui.install_status_label.setText(_("Подготовка...", "Preparing..."))
        subs = []

        def cleanup():
            for name, cb in subs:
                bus.unsubscribe(name, cb)
            subs.clear()
            gui.install_model_button.setEnabled(True)
            gui.install_status_label.setVisible(False)  # Скрываем после завершения

        def on_progress(event):
            if event.data.get('model') == engine:
                status = event.data.get('status', '')
                pr = event.data.get('progress', 0)
                # Сокращаем текст статуса чтобы не распирало панель
                if len(status) > 30:
                    status = status[:27] + "..."
                gui.install_status_label.setText(f"{pr}%")  # Показываем только процент

        def on_finished(event):
            if event.data.get('model') == engine:
                gui.install_status_label.setText(_("Готово", "Done"))
                cleanup()
                apply_asr_install_status(engine)

        def on_failed(event):
            if event.data.get('model') == engine:
                gui.install_status_label.setText(_("Ошибка", "Error"))
                set_pill_called(gui.asr_status_label, _('Ошибка', 'Error'), "warn")
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

    gui.install_model_button.clicked.connect(start_install)

    # Переключатели
    def on_active_toggled(state: int):
        gui._save_setting('MIC_ACTIVE', bool(state))

    def on_instant_toggled(state: int):
        gui._save_setting('MIC_INSTANT_SENT', bool(state))

    gui.mic_active_checkbox.stateChanged.connect(on_active_toggled)
    gui.mic_instant_checkbox.stateChanged.connect(on_instant_toggled)

    # События инициализации (начало/готово)
    def on_asr_init_started(_event):
        set_pill_called(gui.asr_init_status, _("Инициализация...", "Initializing..."), "progress")

    def on_asr_initialized(_event):
        set_pill_called(gui.asr_init_status, _("Готово", "Ready"), "ok")

    bus.subscribe(Events.Speech.ASR_MODEL_INIT_STARTED, on_asr_init_started, weak=False)
    bus.subscribe(Events.Speech.ASR_MODEL_INITIALIZED, on_asr_initialized, weak=False)

    # Инициализация UI
    populate_mics()

    def refresh_engine_ui():
        eng = gui.recognizer_combobox.currentText()
        rebuild_model_settings(eng)
        apply_asr_install_status(eng)

    refresh_engine_ui()
    QTimer.singleShot(400, refresh_engine_ui)


def on_mic_selected(gui, full_device_name=None):
    """
    Устанавливает микрофон по строке вида "Name (ID)".
    Исправлен разбор ID.
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
    """Совместимость: выставляет сохранённый микрофон и активность."""
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