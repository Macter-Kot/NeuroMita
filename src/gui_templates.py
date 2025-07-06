from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit, QComboBox, 
                             QCheckBox, QPushButton, QTextEdit, QSizePolicy)
from PyQt6.QtCore import Qt

from main_logger import logger
from settings_manager import CollapsibleSection, InnerCollapsibleSection
from utils import getTranslationVariant as _

def create_settings_section(gui, parent_layout, title, cfg_list, *, icon_name=None):
    root = CollapsibleSection(title, gui, icon_name=icon_name)
    parent_layout.addWidget(root)
    current_sub = None

    for cfg in cfg_list:
        t = cfg.get('type')

        if t == 'subsection':
            current_sub = InnerCollapsibleSection(cfg.get('label', ''), gui)
            root.add_widget(current_sub)
            continue

        if t == 'end':
            current_sub = None
            continue

        if t == 'text':
            lbl = QLabel(cfg['label'])
            lbl.setObjectName('SeparatorLabel')
            (current_sub or root).add_widget(lbl)
            continue

        parent = (current_sub or root).content

        if t == 'button_group':
            w = create_button_group(gui, parent, cfg.get('buttons', []))
        else:
            w = create_setting_widget(
                gui=gui, parent=parent, label=cfg.get('label'),
                setting_key=cfg.get('key', ''), widget_type=t,
                options=cfg.get('options'), default=cfg.get('default', ''),
                default_checkbutton=cfg.get('default_checkbutton', False),
                validation=cfg.get('validation'), tooltip=cfg.get('tooltip'),
                hide=cfg.get('hide', False), command=cfg.get('command'),
                widget_name=cfg.get('widget_name', cfg.get('key')),
                depends_on=cfg.get('depends_on'),
                hide_when_disabled=cfg.get('hide_when_disabled', False),
                toggle_key=cfg.get('toggle_key'),
                toggle_default=cfg.get('toggle_default'),
            )
        if w:
            (current_sub or root).add_widget(w)

    return root

def create_button_group(gui, parent, buttons_config):
    """Создает горизонтальную группу кнопок."""
    frame = QWidget(parent)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(10)
    
    for btn_config in buttons_config:
        button = QPushButton(btn_config['label'])
        if 'command' in btn_config:
            button.clicked.connect(btn_config['command'])
        layout.addWidget(button)
        
    return frame

def create_setting_widget(
        gui,
        parent,
        label,
        *,
        setting_key: str = '',
        widget_type: str = 'entry',
        options=None,
        default='',
        default_checkbutton=False,
        validation=None,
        tooltip=None,
        hide=False,
        command=None,
        widget_name=None,
        # ───────── ЗАВИСИМОСТИ ─────────
        depends_on: str | None = None,
        hide_when_disabled: bool = False,
        # ───────── «ЧЕКБОКС ВНУТРИ СТРОКИ» ─────────
        toggle_key: str | None = None,
        toggle_default: bool | None = None,
        **kwargs
):
    """
    Создаёт строку настройки:
    • label                – подпись.
    • widget_type          – entry / combobox / checkbutton / button / text.
    • depends_on           – имя виджета-контроллера; если он не активен,
                             наш виджет серый (или скрыт).
    • toggle_key           – если указан, в строку добавляется чекбокс,
                             который хранит значение toggle_key и
                             включает/выключает сам entry.
    """

    #                 1) начальное значение в Settings
    if setting_key and gui.settings.get(setting_key) is None:
        init_val = default_checkbutton if widget_type == 'checkbutton' else default
        gui.settings.set(setting_key, init_val)

    if toggle_key and gui.settings.get(toggle_key) is None:
        gui.settings.set(toggle_key,
                         toggle_default if toggle_default is not None else True)
        
    if widget_type in ('textarea', 'textedit'):
        # --- контейнер для одной настройки ---
        frame = QWidget(parent)
        vlay = QVBoxLayout(frame)
        vlay.setContentsMargins(0, 2, 0, 2)
        vlay.setSpacing(4)

        lbl = QLabel(label)
        lbl.setWordWrap(True)  # длинные подписи переносятся
        vlay.addWidget(lbl)

        widget = QTextEdit()
        widget.setPlainText(str(gui.settings.get(setting_key, default)))

        widget.setMinimumHeight(50)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Expanding)

        vlay.addWidget(widget)

        # сигналы сохранения
        widget.textChanged.connect(
            lambda w=widget: gui._save_setting(setting_key, w.toPlainText())
        )

        if widget_name:
            setattr(gui, widget_name, widget)
            setattr(gui, f"{widget_name}_frame", frame)

        return frame

    #                 2) каркас строки
    frame = QWidget(parent)
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(0, 2, 0, 2)
    layout.setSpacing(10)

    #                 3) label
    lbl = QLabel(label)
    lbl.setMinimumWidth(140)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

    widget = None           # основной контрол строки
    toggle_chk = None       # чекбокс-переключатель (если нужен)

    # ───────────────────────────────────────────────────────────────
    #  ЧЕКБОКС-ПЕРЕКЛЮЧАТЕЛЬ (внутри строки, до основного виджета)
    # ───────────────────────────────────────────────────────────────
    if widget_type == 'entry' and toggle_key:
        toggle_chk = QCheckBox()
        toggle_chk.setChecked(bool(gui.settings.get(toggle_key, True)))

        def _toggle_slot(state):
            enabled = state == Qt.CheckState.Checked.value
            gui._save_setting(toggle_key, enabled)
            if widget:                 # widget появится чуть позже
                widget.setEnabled(enabled)
            lbl.setEnabled(enabled)

        toggle_chk.stateChanged.connect(_toggle_slot)

    # ───────────────────────────────────────────────────────────────
    #                    СОЗДАЁМ ОСНОВНОЙ WIDGET
    # ───────────────────────────────────────────────────────────────
    if widget_type == 'checkbutton':
        widget = QCheckBox()
        widget.setChecked(bool(gui.settings.get(setting_key, default_checkbutton)))

        def _save_check(state):
            val = state == Qt.CheckState.Checked.value
            gui._save_setting(setting_key, val)
            if command:
                command(val)

        widget.stateChanged.connect(_save_check)

        # layout: Label | CheckBox
        layout.addWidget(lbl)
        layout.addWidget(widget, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)

    elif widget_type == 'entry':
        widget = QLineEdit(str(gui.settings.get(setting_key, default)))
        if hide:
            widget.setEchoMode(QLineEdit.EchoMode.Password)

        def _save_entry():
            if validation and not validation(widget.text()):
                widget.setText(str(gui.settings.get(setting_key, default)))
                return
            if not (hide and widget.text() == ''):
                gui._save_setting(setting_key, widget.text())
            if command:
                command(widget.text())

        widget.editingFinished.connect(_save_entry)

        # layout: Label | (toggle_chk?) | LineEdit (stretch)
        layout.addWidget(lbl)
        if toggle_chk:
            layout.addWidget(toggle_chk, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(widget, 1)

    elif widget_type == 'combobox':
        widget = QComboBox()
        if options:
            widget.addItems([str(o) for o in options])
        widget.setCurrentText(str(gui.settings.get(setting_key, default)))

        def _save_combo(text):
            gui._save_setting(setting_key, text)
            if command:
                command()

        widget.currentTextChanged.connect(_save_combo)

        layout.addWidget(lbl)
        if toggle_chk:
            layout.addWidget(toggle_chk, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(widget, 1)

    elif widget_type == 'button':
        widget = QPushButton(label)
        if command:
            widget.clicked.connect(command)
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addStretch()
        button_layout.addWidget(widget)
        button_layout.addStretch()
        layout.addLayout(button_layout)

    elif widget_type == 'text':
        widget = QLabel(label)
        widget.setObjectName("SeparatorLabel")
        layout.addWidget(widget)

    #                 4) tool-tips
    if tooltip and widget:
        widget.setToolTip(tooltip)

    #                 5) сохраняем как атрибуты self
    if widget_name and widget is not None:
        setattr(gui, widget_name, widget)
        setattr(gui, f"{widget_name}_frame", frame)

    # ───────────────────────────────────────────────────────────────
    #                depends_on  (внешняя зависимость)
    # ───────────────────────────────────────────────────────────────
    if depends_on and widget:
        controller = getattr(gui, depends_on, None)

        if not controller:
            logger.warning(f"[depends_on] controller '{depends_on}' not found for '{setting_key}'")
        else:
            def _dep_sync(_=None):
                active = True
                if isinstance(controller, QCheckBox):
                    active = controller.isChecked()
                elif hasattr(controller, "currentText"):
                    active = bool(controller.currentText())
                if hide_when_disabled:
                    frame.setVisible(active)
                else:
                    widget.setEnabled(active)
                    lbl.setEnabled(active)

            _dep_sync()  # начальная синхронизация

            # подключаем сигнал
            if isinstance(controller, QCheckBox):
                controller.stateChanged.connect(_dep_sync)
            elif hasattr(controller, "currentTextChanged"):
                controller.currentTextChanged.connect(_dep_sync)

    if toggle_chk and widget_type == 'entry':
        enabled = toggle_chk.isChecked()
        widget.setEnabled(enabled)
        lbl.setEnabled(enabled)

    return frame