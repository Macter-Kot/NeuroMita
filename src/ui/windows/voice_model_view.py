# voice_model_view.py

import os
import re
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QLineEdit, QComboBox, QCheckBox,
    QMessageBox, QListWidget, QListWidgetItem, QSplitter, QTabWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QCursor

from styles.voice_model_styles import get_stylesheet
from utils import getTranslationVariant as _
from core.events import get_event_bus, Events
from ui.windows.voice_action_windows import VoiceInstallationWindow

try:
    import qtawesome as qta
except Exception:
    qta = None

# ---------- Панель деталей модели ----------
class ModelDetailView(QWidget):
    install_clicked = pyqtSignal(str)
    uninstall_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.models_data = []
        self.current_model_id = None
        self.installed_models = set()

        self.desc_cb = None
        self.clear_desc_cb = None

        self.gpu_vendor = None
        self.gpu_name = None
        self.cuda_devices = []
        self.rtx_check_func = None  # функция, возвращающая bool

        # Хранилище виджетов настроек (key -> {widget, type})
        self.setting_widgets = {}

        main = QVBoxLayout(self)
        main.setContentsMargins(10, 10, 10, 10)
        main.setSpacing(8)

        # Header card
        self.header = QFrame()
        self.header.setObjectName("ModelPanel")
        h = QVBoxLayout(self.header)
        h.setContentsMargins(10, 8, 10, 8)   # компактнее
        h.setSpacing(4)                      # компактнее

        # Title row
        title_row = QHBoxLayout()
        title_row.setSpacing(6)
        self.title_label = QLabel("—")
        self.title_label.setObjectName("TitleLabel")
        title_row.addWidget(self.title_label)
        title_row.addStretch()
        h.addLayout(title_row)

        # Meta chips row (VRAM, GPU, OS, RTX etc) — всё в одну строку
        self.meta_row = QHBoxLayout()
        self.meta_row.setSpacing(4)          # плотнее
        h.addLayout(self.meta_row)

        # Languages (прячем, если пусто)
        self.langs_row = QHBoxLayout()
        self.langs_row.setSpacing(6)
        self.langs_title = QLabel(_("Языки:", "Languages:"))
        self.langs_title.setObjectName("Subtle")
        self.langs_row.addWidget(self.langs_title)
        self.langs_container = QHBoxLayout()
        self.langs_container.setSpacing(6)
        self.langs_row.addLayout(self.langs_container)
        self.langs_row.addStretch()
        h.addLayout(self.langs_row)

        # Описание модели (обычный абзац, без списков)
        self.profile_desc_label = QLabel("—")
        self.profile_desc_label.setWordWrap(True)
        self.profile_desc_label.setObjectName("Subtle")
        h.addWidget(self.profile_desc_label)

        # Предупреждение (AMD и прочее)
        self.warning_label = QLabel("")
        self.warning_label.setObjectName("Warn")
        h.addWidget(self.warning_label)

        # Кнопки
        act = QHBoxLayout()
        act.setContentsMargins(0, 4, 0, 0)
        self.btn_uninstall = QPushButton(_("Удалить", "Uninstall"))
        self.btn_uninstall.setObjectName("DangerButton")
        self.btn_uninstall.clicked.connect(self._on_uninstall)
        self.btn_install = QPushButton(_("Установить", "Install"))
        self.btn_install.setObjectName("SecondaryButton")
        self.btn_install.clicked.connect(self._on_install)
        act.addStretch()
        act.addWidget(self.btn_uninstall)
        act.addWidget(self.btn_install)
        h.addLayout(act)

        main.addWidget(self.header)

        # Settings area
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setWidgetResizable(True)
        self.settings_holder = QWidget()
        self.settings_layout = QVBoxLayout(self.settings_holder)
        self.settings_layout.setContentsMargins(4, 4, 4, 4)
        self.settings_layout.setSpacing(6)
        self.settings_scroll.setWidget(self.settings_holder)
        main.addWidget(self.settings_scroll, 1)

        self.placeholder_settings = QLabel(
            _("Модель не установлена.\nНажмите «Установить», чтобы открыть настройки.",
            "Model is not installed.\nClick “Install” to open settings.")
        )
        self.placeholder_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder_settings.setWordWrap(True)
        self.settings_layout.addWidget(self.placeholder_settings)
        self.settings_layout.addStretch()

    # ---- wiring ----
    def set_models(self, models):
        self.models_data = models

    def set_description_callbacks(self, update_cb, clear_cb):
        self.desc_cb = update_cb
        self.clear_desc_cb = clear_cb

    def set_installed_set(self, installed):
        self.installed_models = set(installed)
        self._update_action_buttons()

    def set_gpu_info(self, vendor=None, name=None, cuda_devices=None):
        self.gpu_vendor = vendor
        self.gpu_name = name
        self.cuda_devices = list(cuda_devices or [])

    def set_rtx_check_func(self, func):
        self.rtx_check_func = func

    # ---- actions ----
    def _on_install(self):
        if self.current_model_id:
            self.install_clicked.emit(self.current_model_id)

    def _on_uninstall(self):
        if self.current_model_id:
            self.uninstall_clicked.emit(self.current_model_id)

    # ---- utils ----
    def _clear_layout(self, layout):
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
            elif it.layout():
                self._clear_layout(it.layout())

    def _make_tag(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("Tag")
        return lab

    def _find_model(self, model_id):
        for m in self.models_data:
            if m.get("id") == model_id:
                return m
        return {}

    def _update_action_buttons(self):
        mid = self.current_model_id
        if not mid:
            self.btn_install.setEnabled(False)
            self.btn_uninstall.setEnabled(False)
            return
        installed = mid in self.installed_models
        self.btn_uninstall.setVisible(installed)
        self.btn_uninstall.setEnabled(installed)
        self.btn_install.setVisible(not installed)

        # AMD compatibility check
        model = self._find_model(mid)
        supported = model.get("gpu_vendor", []) or []
        is_amd_user = (self.gpu_vendor == "AMD")
        is_amd_supported = ("AMD" in supported)
        allow_unsupported = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"

        can_install = True
        install_text = _("Установить", "Install")
        if is_amd_user and not is_amd_supported and not allow_unsupported:
            can_install = False
            install_text = _("Несовместимо с AMD", "Incompatible with AMD")

        self.btn_install.setText(install_text)
        self.btn_install.setEnabled(can_install)

    # external compatibility (controller expects these sometimes)
    def set_button_text(self, text: str):
        btn = self.btn_install if self.btn_install.isVisible() else self.btn_uninstall
        btn.setText(text)

    def set_button_enabled(self, enabled: bool):
        self.btn_install.setEnabled(enabled and self.btn_install.isVisible())
        self.btn_uninstall.setEnabled(enabled and self.btn_uninstall.isVisible())

    # ---- settings (плоский список без секций) ----
    def _attach_hover_handlers(self, widgets, key):
        if self.desc_cb is None and self.clear_desc_cb is None:
            return

        def enter_event(_e, k=key):
            if self.desc_cb:
                self.desc_cb(k)

        def leave_event(_e):
            if self.clear_desc_cb:
                self.clear_desc_cb()

        for w in widgets:
            try:
                w.enterEvent = enter_event
                w.leaveEvent = leave_event
            except Exception:
                pass

    def _add_setting_row(self, key: str, label_text: str, widget_type: str, options: dict, locked: bool = False):
        # строка-обертка, чтобы проще управлять отступами
        row_frame = QFrame()
        row_frame.setObjectName("SettingRow")
        row = QHBoxLayout(row_frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        # Левая «пилюля» с названием
        label_frame = QFrame()
        label_frame.setObjectName("SettingLabel")
        label_frame.setFixedHeight(28)  # Фиксированная высота
        label_layout = QHBoxLayout(label_frame)
        label_layout.setContentsMargins(10, 0, 10, 0)  # без вертикального padding
        lab = QLabel(label_text)
        if locked:
            lab.setStyleSheet("color: #888888;")
        label_layout.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)

        # Правая часть с контролом
        widget_frame = QFrame()
        widget_frame.setObjectName("SettingWidget")
        widget_frame.setFixedHeight(28)  # Фиксированная высота, такая же как у лейбла
        widget_layout = QHBoxLayout(widget_frame)
        widget_layout.setContentsMargins(0, 0, 0, 0)  # минимальные отступы для центрирования
        widget_layout.setSpacing(0)

        w = None
        current = options.get("default")

        if widget_type == "entry":
            w = QLineEdit()
            w.setEnabled(not locked)
            if current is not None:
                w.setText(str(current))
            widget_layout.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)

        elif widget_type == "combobox":
            w = QComboBox()
            values = options.get("values", [])
            if not isinstance(values, (list, tuple)):
                values = []
            w.addItems([str(v) for v in values])
            w.setEnabled(not locked)
            if current is not None and values:
                try:
                    idx = [str(v) for v in values].index(str(current))
                    w.setCurrentIndex(idx)
                except ValueError:
                    w.setCurrentIndex(0 if values else -1)
            widget_layout.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)

        elif widget_type == "checkbutton":
            w = QCheckBox()
            w.setEnabled(not locked)
            val = False
            if isinstance(current, str):
                val = current.lower() == "true"
            elif current is not None:
                val = bool(current)
            w.setChecked(val)
            widget_layout.addWidget(w, 0, Qt.AlignmentFlag.AlignVCenter)
            widget_layout.addStretch()

        # Hover-описания
        self._attach_hover_handlers(
            [label_frame, lab, widget_frame] + ([w] if w is not None else []),
            key
        )

        row.addWidget(label_frame, 4)
        row.addWidget(widget_frame, 6)

        self.settings_layout.addWidget(row_frame)
        self.setting_widgets[key] = {"widget": w, "type": widget_type}

    def build_settings_for(self, model_id: str):
        # Очистка области настроек и хранилища виджетов
        while self.settings_layout.count():
            itm = self.settings_layout.takeAt(0)
            if itm.widget():
                itm.widget().deleteLater()
        self.setting_widgets.clear()

        installed = model_id in self.installed_models
        if not installed:
            self.placeholder_settings = QLabel(
                _("Модель не установлена.\nНажмите «Установить», чтобы открыть настройки.",
                  "Model is not installed.\nClick “Install” to open settings.")
            )
            self.placeholder_settings.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.placeholder_settings.setWordWrap(True)
            self.settings_layout.addWidget(self.placeholder_settings)
            self.settings_layout.addStretch()
            return

        model = self._find_model(model_id)
        adapted_settings = model.get("settings", [])

        # Плоский список строк
        for s in adapted_settings:
            key = s.get("key")
            label = s.get("label", key)
            typ = s.get("type")
            opts = s.get("options", {})
            locked = bool(s.get("locked", False))
            if key and typ:
                self._add_setting_row(key, label, typ, opts, locked)

        self.settings_layout.addStretch()

    def get_current_settings_values(self) -> dict:
        values = {}
        for key, d in self.setting_widgets.items():
            w = d["widget"]
            if isinstance(w, QComboBox):
                values[key] = w.currentText()
            elif isinstance(w, QLineEdit):
                values[key] = w.text()
            elif isinstance(w, QCheckBox):
                values[key] = w.isChecked()
        return values

    # ---- public API for view ----
    def update_for_model(self, model_id: str, models: list, model_desc_text: str):
        self.set_models(models)
        self.current_model_id = model_id
        model = self._find_model(model_id)

        # Title
        self.title_label.setText(model.get("name", model_id))

        # Meta chips (в одну строку, компактно)
        meta_chips = []

        # VRAM
        min_vram = model.get("min_vram")
        rec_vram = model.get("rec_vram")
        if min_vram or rec_vram:
            if min_vram and rec_vram:
                vram_text = f"VRAM: {min_vram}-{rec_vram}GB"
            else:
                vram_text = f"VRAM: {min_vram or rec_vram}GB"
            meta_chips.append(
                self._make_chip(
                    vram_text,
                    "info",
                    icon_names=["mdi.memory", "fa5s.memory", "fa5s.microchip"],
                    icon_color="#b388ff"
                )
            )

        # GPU vendors
        vendors = model.get("gpu_vendor", []) or []
        if vendors:
            meta_chips.append(
                self._make_chip(
                    f"GPU: {', '.join(vendors)}",
                    "info",
                    icon_names=["mdi.graphics-card", "mdi.gpu", "fa5s.microchip"],
                    icon_color="#8bb6ff"
                )
            )

        # OS (если есть)
        os_list = model.get("os", [])
        if os_list:
            os_display = ", ".join(os_list)
            first_os = str(os_list[0]).lower()
            if "win" in first_os:
                os_icons = ["fa5b.windows", "mdi.microsoft-windows", "mdi.windows"]
            elif "mac" in first_os or "darwin" in first_os or "osx" in first_os:
                os_icons = ["fa5b.apple", "mdi.apple"]
            elif "linux" in first_os:
                os_icons = ["fa5b.linux", "mdi.linux"]
            else:
                os_icons = ["fa5s.server", "fa5s.desktop", "mdi.monitor"]
            meta_chips.append(
                self._make_chip(
                    f"OS: {os_display}",
                    "info",
                    icon_names=os_icons,
                    icon_color="#9aa7ff"
                )
            )

        # RTX 30+/40+ (если требуется)
        if model.get("rtx30plus", False):
            meets = self.rtx_check_func() if callable(self.rtx_check_func) else False
            meta_chips.append(
                self._make_chip(
                    "RTX 30+",
                    "ok" if meets else "warn",
                    icon_names=["fa5s.bolt", "mdi.flash"],
                    icon_color="#f2da6b"
                )
            )

        # NEW: интенты (макс. 2 штуки, чтобы не раздувать карточку)
        for it in (model.get("intents") or [])[:2]:
            meta_chips.append(
                self._make_chip(
                    it, "info",
                    icon_names=["fa5s.bullseye", "mdi.target-variant"],
                    icon_color="#cfa8ff"
                )
            )

        self._set_chips(self.meta_row, meta_chips)

        # Languages (компактный режим: показываем первые N, остальные — в +N с тултипом)
        self._clear_layout(self.langs_container)
        langs = model.get("languages", []) or []
        if langs:
            self.langs_title.setVisible(True)

            # Сколько бейджей показывать максимально на панели (чтобы не растягивать её)
            max_lang_chips = 8  # можно изменить на 6, если хочется ещё компактнее

            visible = langs[:max_lang_chips]
            hidden = langs[max_lang_chips:]

            for lg in visible:
                self.langs_container.addWidget(self._make_tag(lg))

            if hidden:
                more_tag = self._make_tag(f"+{len(hidden)}")
                # отдельный стиль для “+N”, чтобы визуально отличался
                more_tag.setObjectName("TagMore")
                # полный список в тултипе (по строкам)
                more_tag.setToolTip("\n".join(hidden))
                self.langs_container.addWidget(more_tag)
        else:
            self.langs_title.setVisible(False)

        # AMD warning
        supported = model.get("gpu_vendor", []) or []
        is_amd_user = (self.gpu_vendor == "AMD")
        is_amd_supported = ("AMD" in supported)
        allow_unsupported = os.environ.get("ALLOW_UNSUPPORTED_GPU", "0") == "1"
        if is_amd_user and not is_amd_supported and allow_unsupported:
            self.warning_label.setText(_("Может не работать на AMD!", "May not work on AMD!"))
        elif is_amd_user and not is_amd_supported and not allow_unsupported:
            self.warning_label.setText(_("Несовместимо с AMD.", "Incompatible with AMD."))
        else:
            self.warning_label.setText("")

        # Описание модели — обычный абзац
        self.profile_desc_label.setText(model_desc_text)

        # Кнопки
        self._update_action_buttons()

        # Настройки
        self.build_settings_for(model_id)

    def _qta_pixmap(self, names, color="#cccccc", size=12):
        """Возвращает QPixmap первой доступной иконки из списка имен qtawesome."""
        if not 'qta' in globals() or qta is None:
            return None
        # names может быть строкой или списком
        seq = names if isinstance(names, (list, tuple)) else [names]
        for n in seq:
            try:
                icon = qta.icon(n, color=color)
                pm = icon.pixmap(size, size)
                if pm and not pm.isNull():
                    return pm
            except Exception:
                continue
        return None
    
    def _make_chip(self, text: str, kind: str = "info", icon_names=None, icon_color="#bbbbbb"):
        """
        Делаем компактный чип: [иконка] [текст]
        kind: info | ok | warn  — влияет на фон/границу.
        """
        from styles.main_styles import get_theme
        theme = get_theme()

        # Базовые цвета
        if kind == "warn":
            bg = theme.get("warn_bg", "rgba(255,120,120,0.08)")
            border = theme.get("warn_border", "rgba(255,120,120,0.25)")
            fg = theme.get("warn_text", "#ffb4b4")
        elif kind == "ok":
            # аккуратный зеленый фон
            bg = "rgba(61,166,110,0.16)"
            border = "rgba(61,166,110,0.45)"
            fg = "#9be2bc"
        else:
            bg = theme.get("chip_bg", "rgba(255,255,255,0.06)")
            border = theme.get("outline", "rgba(255,255,255,0.06)")
            fg = theme.get("text", "#e6e6eb")

        frame = QFrame()
        frame.setObjectName("ChipInfo")  # имя не критично, стилизуем локально
        # Стили локально, чтобы не зависеть от QSS-правок
        frame.setStyleSheet(
            f"QFrame#ChipInfo {{"
            f"  background-color: {bg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 4px;"
            f"}}"
            f"QFrame#ChipInfo QLabel {{"
            f"  color: {fg};"
            f"}}"
        )

        lay = QHBoxLayout(frame)
        lay.setContentsMargins(6, 2, 6, 2)  # компактно
        lay.setSpacing(4)

        # Иконка (qtawesome) или точка-маникер
        pm = self._qta_pixmap(icon_names, color=icon_color, size=12) if icon_names else None
        if pm is not None:
            ic = QLabel()
            ic.setPixmap(pm)
            ic.setFixedSize(14, 14)
            lay.addWidget(ic, 0, Qt.AlignmentFlag.AlignVCenter)
        else:
            dot = QLabel("•")
            dot.setStyleSheet(f"color: {icon_color}; padding: 0; margin: 0; font-size: 10pt;")
            lay.addWidget(dot, 0, Qt.AlignmentFlag.AlignVCenter)

        lab = QLabel(text)
        lab.setStyleSheet("font-size: 8pt; padding: 0; margin: 0;")
        lay.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)

        return frame

    def _set_chips(self, layout: QHBoxLayout, chips):
        self._clear_layout(layout)
        for ch in chips:
            layout.addWidget(ch, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch()

    def _format_description_html(self, text: str) -> str:
        """
        Делает маркированный список, если описаний несколько (по предложениям/переводам строк).
        """
        if not text:
            return "—"
        parts = [p.strip() for p in re.split(r"(?:\n+|(?<=[.!?])\s+)", text) if p and len(p.strip()) > 2]
        parts = [p for p in parts if p not in ("-", "—")]
        if len(parts) >= 2:
            items = "".join(f"<li>{p}</li>" for p in parts[:8])
            return f"<ul style='margin: 6px 0 0 18px;'>{items}</ul>"
        return text


# ---------- Главное окно настроек ----------
class VoiceModelSettingsView(QWidget):

    update_description_signal = pyqtSignal(str)
    clear_description_signal = pyqtSignal()
    install_started_signal = pyqtSignal(str)
    install_finished_signal = pyqtSignal(dict)
    uninstall_started_signal = pyqtSignal(str)
    uninstall_finished_signal = pyqtSignal(dict)
    refresh_panels_signal = pyqtSignal()
    refresh_settings_signal = pyqtSignal()

    ask_question_signal = pyqtSignal(str, str, object, object)
    create_voice_action_window_signal = pyqtSignal(str, str, object, object)

    def __init__(self):
        super().__init__()

        self.setWindowTitle(_("Настройки и Установка Локальных Моделей", "Settings and Installation of Local Models"))
        self.setMinimumSize(900, 650)
        self.resize(1100, 720)

        # Style
        self.setStyleSheet(get_stylesheet())

        # EB
        self.event_bus = get_event_bus()

        # State
        self._cached_dependencies_status = None
        self.models_data = []
        self.installed_models = set()

        # UI refs
        self.desc_label = None
        self.tabs = None
        self.list = None
        self.search = None
        self.detail = None

        self._build_ui()

        # Signals
        self.update_description_signal.connect(self._on_update_description)
        self.clear_description_signal.connect(self._on_clear_description)
        self.install_started_signal.connect(self._on_install_started)
        self.install_finished_signal.connect(self._on_install_finished)
        self.uninstall_started_signal.connect(self._on_uninstall_started)
        self.uninstall_finished_signal.connect(self._on_uninstall_finished)
        self.refresh_panels_signal.connect(self._on_refresh_panels)
        self.refresh_settings_signal.connect(self._on_refresh_settings)
        self.ask_question_signal.connect(self._on_ask_question)
        self.create_voice_action_window_signal.connect(self._on_create_voice_action_window)

        # Data
        self._initialize_data()

    # ---------- UI build ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Компактная зона подсказок сверху (для hover-описаний)
        desc_frame = QFrame()
        desc_frame.setObjectName("DescriptionFrame")
        desc_frame.setFixedHeight(60)  # ещё компактнее
        d_l = QVBoxLayout(desc_frame)
        d_l.setContentsMargins(10, 6, 10, 6)

        desc_title = QLabel(_("Подсказка", "Hint"))
        desc_title.setStyleSheet("font-weight: bold; font-size: 9pt;")
        d_l.addWidget(desc_title)

        self.desc_label = QLabel("")
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #cccccc; font-size: 9pt;")
        self.desc_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        d_l.addWidget(self.desc_label, 1)

        root.addWidget(desc_frame)

        # Tabs
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)

        # Tab: Models
        self.tab_models = QWidget()
        t_l = QVBoxLayout(self.tab_models)
        t_l.setContentsMargins(0, 0, 0, 0)
        t_l.setSpacing(6)

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Orientation.Horizontal)

        # Left
        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Поиск моделей...", "Search models..."))
        self.search.textChanged.connect(self._apply_filter)
        left_l.addWidget(self.search)

        self.list = QListWidget()
        self.list.setMouseTracking(True)
        self.list.itemSelectionChanged.connect(self._on_selection_changed)
        self.list.itemEntered.connect(self._on_item_hovered)
        left_l.addWidget(self.list, 1)

        self.splitter.addWidget(left)

        # Right: detail
        right = QWidget()
        right_l = QVBoxLayout(right)
        right_l.setContentsMargins(0, 0, 0, 0)

        self.detail = ModelDetailView()
        # description hover callbacks
        self.detail.set_description_callbacks(
            lambda key: self.event_bus.emit(Events.VoiceModel.UPDATE_DESCRIPTION, key),
            lambda: self.event_bus.emit(Events.VoiceModel.CLEAR_DESCRIPTION)
        )
        # wiring install/uninstall
        self.detail.install_clicked.connect(self._on_install_clicked)
        self.detail.uninstall_clicked.connect(self._on_uninstall_clicked)

        right_l.addWidget(self.detail, 1)
        self.splitter.addWidget(right)
        self.splitter.setSizes([300, 800])

        t_l.addWidget(self.splitter, 1)
        self.tabs.addTab(self.tab_models, _("Модели", "Models"))

        # Tab: Dependencies
        self.tab_deps = QWidget()
        dl = QVBoxLayout(self.tab_deps)
        dl.setContentsMargins(10, 10, 10, 10)
        dl.setSpacing(8)

        deps_title = QLabel(_("Системные Зависимости", "System Dependencies"))
        deps_title.setObjectName("TitleLabel")
        dl.addWidget(deps_title)

        self._build_dependencies_panel(dl)
        dl.addStretch()
        self.tabs.addTab(self.tab_deps, _("Зависимости", "Dependencies"))

        # Bottom buttons
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addStretch()
        btn_close = QPushButton(_("Закрыть", "Close"))
        btn_close.clicked.connect(self._on_close_clicked)
        btn_save = QPushButton(_("Сохранить", "Save"))
        btn_save.setObjectName("PrimaryButton")
        btn_save.clicked.connect(self._on_save_clicked)
        bottom.addWidget(btn_close)
        bottom.addWidget(btn_save)
        root.addLayout(bottom)

    # ---------- Data init ----------
    def _initialize_data(self):
        self.models_data = self._get_models_data()
        self.installed_models = self._get_installed_models()
        self._cached_dependencies_status = self._get_dependencies_status()

        # Set default description
        self._on_clear_description()

        # Populate list and select first
        self._populate_list()
        if self.list.count():
            self.list.setCurrentRow(0)

        # Pass GPU info and RTX checker to detail
        vendor = self._cached_dependencies_status.get('detected_gpu_vendor')
        self.detail.set_gpu_info(vendor=vendor, name=None, cuda_devices=[])
        self.detail.set_rtx_check_func(lambda: bool(self._check_gpu_rtx30_40()))

    # ---------- EventBus helpers ----------
    def _get_models_data(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_MODEL_DATA)
        return results[0] if results else []

    def _get_installed_models(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_INSTALLED_MODELS)
        return results[0] if results else set()

    def _get_dependencies_status(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_DEPENDENCIES_STATUS)
        return results[0] if results else {}

    def _get_default_description(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_DEFAULT_DESCRIPTION)
        return results[0] if results else ""

    def _get_model_description(self, model_id):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.GET_MODEL_DESCRIPTION, model_id)
        return results[0] if results else self._get_default_description()

    def _check_gpu_rtx30_40(self):
        results = self.event_bus.emit_and_wait(Events.VoiceModel.CHECK_GPU_RTX30_40)
        return results[0] if results else False

    # ---------- Dependencies tab ----------
    def _build_dependencies_panel(self, layout: QVBoxLayout):
        st = self._cached_dependencies_status or {}

        if st.get("show_triton_checks", False):
            row = QHBoxLayout()
            row.setSpacing(16)
            for text, ok in [
                (_("CUDA Toolkit:", "CUDA Toolkit:"), st.get("cuda_found", False)),
                (_("Windows SDK:", "Windows SDK:"), st.get("winsdk_found", False)),
                (_("MSVC:", "MSVC:"), st.get("msvc_found", False))
            ]:
                sub = QHBoxLayout()
                sub.setSpacing(6)
                lab = QLabel(text)
                val = QLabel(_("Найден", "Found") if ok else _("Не найден", "Not Found"))
                val.setStyleSheet(f"color: {'lightgreen' if ok else '#FF6A6A'};")
                sub.addWidget(lab)
                sub.addWidget(val)
                row.addLayout(sub)
            row.addStretch()
            layout.addLayout(row)

            if not (st.get("cuda_found") and st.get("winsdk_found") and st.get("msvc_found")):
                warn = QHBoxLayout()
                wlab = QLabel(_("⚠️ Для моделей Fish Speech+ / +RVC могут потребоваться все компоненты.",
                                "⚠️ Fish Speech+ / +RVC models may require all components."))
                wlab.setStyleSheet("color: orange; font-weight: bold;")
                warn.addWidget(wlab)
                link = QLabel(_("[Документация]", "[Documentation]"))
                link.setObjectName("Link")
                link.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
                link.mousePressEvent = lambda e: self.event_bus.emit(Events.VoiceModel.OPEN_DOC, "installation_guide.html")
                warn.addWidget(link)
                warn.addStretch()
                layout.addLayout(warn)
        elif not st.get("triton_installed", False):
            warn = QLabel(_("Triton не установлен (нужен для Fish Speech+ / +RVC).",
                             "Triton not installed (required for Fish Speech+ / +RVC)."))
            warn.setStyleSheet("color: orange;")
            layout.addWidget(warn)
        else:
            info = QLabel(_("Проверка зависимостей Triton доступна только в Windows.",
                            "Triton dependency check is only available on Windows."))
            info.setObjectName("Subtle")
            layout.addWidget(info)

    # ---------- Description helpers ----------
    def _on_update_description(self, text: str):
        if self.desc_label:
            self.desc_label.setText(text)

    def _on_clear_description(self):
        if self.desc_label:
            self.desc_label.setText(self._get_default_description())

    # ---------- List / Filter ----------
    def _populate_list(self):
        self.list.clear()
        for m in self.models_data:
            self._add_model_item(m)
        self._refresh_list_visuals()

    def _base_label_for(self, model_id: str) -> str:
        for m in self.models_data:
            if m.get("id") == model_id:
                return m.get("name", model_id)
        return model_id

    def _add_model_item(self, model: dict):
        name = model.get("name", model["id"])
        item = QListWidgetItem(name)
        item.setData(Qt.ItemDataRole.UserRole, model["id"])
        item.setToolTip(self._get_model_description(model["id"]))
        self.list.addItem(item)

    def _refresh_list_visuals(self):
        for i in range(self.list.count()):
            item = self.list.item(i)
            mid = item.data(Qt.ItemDataRole.UserRole)
            base = self._base_label_for(mid)
            if mid in self.installed_models:
                item.setText(f"🟢 {base}")
            else:
                item.setText(f"⚪ {base}")

    def _apply_filter(self, text: str):
        t = (text or "").strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            base = self._base_label_for(item.data(Qt.ItemDataRole.UserRole)).lower()
            item.setHidden(t not in base)

    def _on_selection_changed(self):
        item = self.list.currentItem()
        if not item:
            return
        model_id = item.data(Qt.ItemDataRole.UserRole)
        # верхний блок оставляем как “подсказку по ховеру”
        self._on_clear_description()
        # детальная панель справа показывает текст описания модели (абзац)
        self.detail.set_installed_set(self.installed_models)
        self.detail.update_for_model(model_id, self.models_data, self._get_model_description(model_id))

    def _on_item_hovered(self, item: QListWidgetItem):
        model_id = item.data(Qt.ItemDataRole.UserRole)
        self._on_update_description(self._get_model_description(model_id))

    # ---------- Install / Uninstall ----------
    def _on_install_clicked(self, model_id: str):
        models_data = self.models_data
        model_data = next((m for m in models_data if m["id"] == model_id), None)
        if not model_data:
            return

        model_name = model_data.get("name", model_id)
        window = VoiceInstallationWindow(
            self.window() if self.window() else self,
            _(f"Скачивание {model_name}", f"Downloading {model_name}"),
            _("Подготовка...", "Preparing...")
        )
        window.show()

        self.event_bus.emit(Events.VoiceModel.INSTALL_MODEL, {
            'model_id': model_id,
            'progress_callback': window.update_progress,
            'status_callback': window.update_status,
            'log_callback': window.update_log,
            'window': window
        })

    def _on_uninstall_clicked(self, model_id: str):
        self.event_bus.emit(Events.VoiceModel.UNINSTALL_MODEL, {'model_id': model_id})

    def _on_save_clicked(self):
        self.event_bus.emit(Events.VoiceModel.SAVE_SETTINGS)

    def _on_close_clicked(self):
        self.event_bus.emit(Events.VoiceModel.CLOSE_DIALOG)

    # ---------- Install/Uninstall UI state ----------
    def _on_install_started(self, model_id):
        self.detail.set_button_text(_("Загрузка...", "Downloading..."))
        self.detail.set_button_enabled(False)

    def _on_install_finished(self, data):
        self.installed_models = self._get_installed_models()
        self._refresh_list_visuals()
        self._on_selection_changed()

    def _on_uninstall_started(self, model_id):
        self.detail.set_button_text(_("Удаление...", "Uninstalling..."))
        self.detail.set_button_enabled(False)

    def _on_uninstall_finished(self, data):
        self.installed_models = self._get_installed_models()
        self._refresh_list_visuals()
        self._on_selection_changed()

    def _on_refresh_panels(self):
        self.models_data = self._get_models_data()
        self.installed_models = self._get_installed_models()
        self._populate_list()

    def _on_refresh_settings(self):
        self._cached_dependencies_status = self._get_dependencies_status()
        self.detail.set_gpu_info(vendor=self._cached_dependencies_status.get('detected_gpu_vendor'))
        self._on_selection_changed()

    # ---------- API for controller compatibility ----------
    def set_button_text(self, model_id, text):
        cur = self.list.currentItem()
        if cur and cur.data(Qt.ItemDataRole.UserRole) == model_id:
            self.detail.set_button_text(text)

    def set_button_enabled(self, model_id, enabled):
        cur = self.list.currentItem()
        if cur and cur.data(Qt.ItemDataRole.UserRole) == model_id:
            self.detail.set_button_enabled(enabled)

    def get_section_values(self, model_id):
        cur = self.list.currentItem()
        if cur and cur.data(Qt.ItemDataRole.UserRole) == model_id:
            return self.detail.get_current_settings_values()
        return {}

    def get_all_section_values(self):
        # сохраняем настройки только текущей выбранной модели
        values = {}
        cur = self.list.currentItem()
        if cur:
            mid = cur.data(Qt.ItemDataRole.UserRole)
            values[mid] = self.detail.get_current_settings_values()
        return values

    # ---------- Dialog helpers for controller ----------
    @pyqtSlot(str, str, object, object)
    def _on_ask_question(self, title, message, result_holder, local_loop):
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        result_holder["answer"] = (reply == QMessageBox.StandardButton.Yes)
        local_loop.quit()

    @pyqtSlot(str, str, object, object)
    def _on_create_voice_action_window(self, title, status, result_holder, local_loop):
        from ui.windows.voice_action_windows import VoiceActionWindow
        window = VoiceActionWindow(self.window() or self, title, status)
        window.show()
        result_holder["window"] = window
        local_loop.quit()

    # ---------- Messages ----------
    def show_warning(self, title, message):
        QMessageBox.warning(self, title, message)

    def show_critical(self, title, message):
        QMessageBox.critical(self, title, message)

    def show_question(self, title, message):
        reply = QMessageBox.question(
            self, title, message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        return reply == QMessageBox.StandardButton.Yes