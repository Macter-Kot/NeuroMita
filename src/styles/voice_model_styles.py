# styles/voice_model_styles.py
from styles.main_styles import get_stylesheet as get_main_stylesheet, get_theme
from utils import render_qss

VOICE_TEMPLATE = """
/* ===== Voice Models window — tweaks on top of main theme ===== */

/* Splitter */
QSplitter::handle {
    background: {outline};
    width: 4px;
    border-radius: 2px;
}

/* Top description card */
QFrame#DescriptionFrame {
    background-color: {card_bg};
    border: 1px solid {card_border};
    border-radius: 12px;
}

/* Model profile card (right) */
QFrame#ModelPanel {
    background-color: {card_bg};
    border: 1px solid {card_border};
    border-radius: 12px;
}

/* Collapsible section header/content */
QWidget#CollapsibleHeader, QFrame#CollapsibleHeader {
    background-color: {chip_bg};
    border-radius: 10px;
}
QWidget#CollapsibleHeader:hover, QFrame#CollapsibleHeader:hover {
    background-color: {chip_hover};
}
QWidget#CollapsibleContent, QFrame#CollapsibleContent {
    background-color: transparent;
}

/* Settings two-column rows */
QFrame#SettingLabel {
    background-color: {chip_bg};
    border: 1px solid {border_soft};
    border-radius: 8px;
}
QFrame#SettingWidget {
    background-color: transparent;
}

/* Role labels */
QLabel#TitleLabel {
    color: {text};
    font-weight: 700;
    font-size: 12pt;
}
QLabel#Subtle { color: {muted}; }
QLabel#Warn {
    color: {warn_text};
    font-weight: 700;
}
QLabel#RTX {
    font-size: 7pt;
    font-weight: 700;
}
QLabel#Link {
    color: {link};
    font-weight: 600;
    text-decoration: underline;
}

/* Tags (languages, chips) */
QLabel#Tag {
    background-color: {chip_bg};
    color: {text};
    border: 1px solid {outline};
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 8pt;
}

/* Buttons mapping for this window */
QPushButton#PrimaryButton {
    background-color: {accent};
    color: #ffffff;
    border: 1px solid {accent_border};
}
QPushButton#PrimaryButton:hover { background-color: {accent_hover}; }
QPushButton#PrimaryButton:pressed { background-color: {accent_pressed}; }

QPushButton#SecondaryButton {
    background-color: {chip_bg};
    color: {text};
    border: 1px solid {outline};
}
QPushButton#SecondaryButton:hover { background-color: {chip_hover}; }
QPushButton#SecondaryButton:pressed { background-color: {chip_pressed}; }
QPushButton#SecondaryButton:disabled {
    background-color: {btn_disabled_bg};
    color: {btn_disabled_fg};
    border: 1px solid {outline};
}

QPushButton#DangerButton {
    background-color: {danger};
    color: #ffffff;
    border: 1px solid rgba(214,69,69,0.35);
}
QPushButton#DangerButton:hover { background-color: {danger_hover}; }
QPushButton#DangerButton:pressed { background-color: {danger_pressed}; }

/* Models list (left) */
QListWidget {
    background: {panel_bg};
    border: 1px solid {border_soft};
    border-radius: 10px;
    padding: 4px;
    outline: 0; /* убираем контур при фокусе */
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 6px;
}
QListWidget::item:hover { background: {chip_bg}; }
QListWidget::item:selected {
    background: {chip_hover};
    color: #ffffff;
}

/* Selected item (active) */
QListView::item:selected:active { background: {chip_hover}; }

/* ===== Remove focus outlines globally where possible ===== */
QWidget:focus { outline: none; }
QAbstractItemView:focus { outline: none; }
QListView:focus, QTreeView:focus, QTableView:focus, QListWidget:focus { outline: none; }
QScrollArea:focus { outline: none; }
QTabBar::tab:focus { outline: none; }
QComboBox:focus { outline: none; }
QLineEdit:focus { outline: none; }
QPushButton:focus { outline: none; }  /* рамка остаётся за счёт border из base theme при необходимости */
"""

def get_stylesheet(overrides: dict | None = None) -> str:
    theme = get_theme()
    if overrides:
        theme.update(overrides)

    base_qss = get_main_stylesheet(overrides)  # базовая тема приложения
    voice_qss = render_qss(VOICE_TEMPLATE, theme)  # окно-специфичные правки

    return base_qss + "\n\n" + voice_qss