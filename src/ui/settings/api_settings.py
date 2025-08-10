from PyQt6.QtCore import QTimer, Qt, QSize, QStringListModel, pyqtSignal, QObject
from PyQt6.QtGui import QPainter, QPixmap, QColor, QFont, QFontMetrics, QPalette, QDesktopServices
from PyQt6.QtWidgets import (QComboBox, QMessageBox, QLabel, QLineEdit,
                             QStyledItemDelegate, QStyle, QHBoxLayout, QVBoxLayout,
                             QPushButton, QToolButton, QCheckBox, QCompleter,
                             QFileDialog, QInputDialog, QWidget, QFrame, QListWidget,
                             QListWidgetItem, QAbstractItemView, QSizePolicy, QSpacerItem)
import qtawesome as qta

from utils import _
from core.events import get_event_bus, Events
from main_logger import logger


class ProviderDelegate(QStyledItemDelegate):
    _free_pm = None

    @classmethod
    def _free_pixmap(cls):
        if cls._free_pm is None:
            font = QFont("Segoe UI", 7, QFont.Weight.Bold)
            metrics = QFontMetrics(font)
            text_w = metrics.horizontalAdvance("FREE")
            w, h = text_w + 8, 14
            pm = QPixmap(w, h)
            pm.fill(Qt.GlobalColor.transparent)

            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor("#4CAF50"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(0, 0, w, h, 3, 3)

            p.setPen(QColor("#ffffff"))
            p.setFont(font)
            p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "FREE")
            p.end()

            cls._free_pm = pm
        return cls._free_pm

    def __init__(self, parent=None):
        super().__init__(parent)
        self.presets_meta = {}

    def set_presets_meta(self, presets_meta):
        self.presets_meta = {p.id: p for p in presets_meta}

    def paint(self, painter, option, index):
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        else:
            painter.fillRect(option.rect, option.palette.base())

        preset_id = index.data(Qt.ItemDataRole.UserRole)
        text = index.data()
        
        if preset_id and preset_id in self.presets_meta:
            preset = self.presets_meta[preset_id]
            pricing = preset.pricing
        else:
            pricing = ""

        dollar_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        ascent = QFontMetrics(dollar_font).ascent()

        x = option.rect.x() + 4
        y = option.rect.y() + (option.rect.height() - 16) // 2

        if pricing == "free":
            painter.drawPixmap(x, y, self._free_pixmap())
            x += self._free_pixmap().width() + 6

        elif pricing == "paid":
            painter.setPen(QColor("#FFC107"))
            painter.setFont(dollar_font)
            painter.drawText(x, y + ascent, "$")
            x += 12

        elif pricing == "mixed":
            painter.drawPixmap(x, y, self._free_pixmap())
            x += self._free_pixmap().width() + 4

            painter.setPen(QColor("#666"))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(x, y + 10, "/")
            x += 8

            painter.setPen(QColor("#FFC107"))
            painter.setFont(dollar_font)
            painter.drawText(x, y + ascent, "$")
            x += 12

        painter.setPen(option.palette.color(
            QPalette.ColorRole.HighlightedText
            if option.state & QStyle.StateFlag.State_Selected
            else QPalette.ColorRole.Text))
        painter.setFont(option.font)
        txt_rect = option.rect.adjusted(x - option.rect.x(), 0, -4, 0)
        painter.drawText(txt_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)

    def sizeHint(self, option, index):
        sz = super().sizeHint(option, index)
        return sz.expandedTo(QSize(140, 24))


class TestConnectionSignals(QObject):
    test_completed = pyqtSignal(dict)


class CustomPresetListItem(QListWidgetItem):
    def __init__(self, preset_id, name, has_changes=False):
        super().__init__()
        self.preset_id = preset_id
        self.base_name = name
        self.has_changes = has_changes
        self.update_display()
    
    def update_changes_indicator(self, has_changes):
        self.has_changes = has_changes
        self.update_display()
    
    def update_display(self):
        display_text = self.base_name
        if self.has_changes:
            display_text = f"{self.base_name}   *"
        self.setText(display_text)


def setup_api_controls(self, parent):
    self.event_bus = get_event_bus()
    self.test_signals = TestConnectionSignals()
    
    self.current_preset_id = None
    self.current_preset_data = {}
    self.is_loading_preset = False
    self.original_preset_state = {}
    self.custom_presets_list_items = {}
    self.pending_changes = {}
    self.api_settings_container = None

    def _add_custom_preset():
        name, ok = QInputDialog.getText(self, _("Новый пресет", "New preset"),
                                    _("Название пресета:", "Preset name:"))
        if not ok or not name.strip():
            return
        
        preset_data = {
            'name': name.strip(),
            'id': None,
            'pricing': 'mixed',
            'url': '',
            'default_model': '',
            'key': '',
            'known_models': [],
            'use_request': False,
            'is_g4f': False
        }
        
        # Просто сохраняем, без немедленной перезагрузки списка - это сделает событие PRESET_SAVED
        result = self.event_bus.emit_and_wait(Events.ApiPresets.SAVE_CUSTOM_PRESET,
                                            {'data': preset_data}, timeout=1.0)
        if not result or not result[0]:
            logger.error("Failed to create new preset")
            return

    def _remove_custom_preset():
        current_item = self.custom_presets_list.currentItem()
        if not current_item or not isinstance(current_item, CustomPresetListItem):
            return
        
        if current_item.has_changes:
            reply = QMessageBox.question(self, _("Несохраненные изменения", "Unsaved changes"),
                                        _("Есть несохраненные изменения. Удалить пресет?",
                                          "There are unsaved changes. Delete preset?"),
                                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        reply = QMessageBox.question(self, _("Удалить пресет", "Delete preset"),
                                    _("Удалить выбранный пресет?", "Delete selected preset?"),
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            self.event_bus.emit(Events.ApiPresets.DELETE_CUSTOM_PRESET, {'id': current_item.preset_id})

    def _move_preset_up():
        current_row = self.custom_presets_list.currentRow()
        if current_row > 0:
            item = self.custom_presets_list.takeItem(current_row)
            self.custom_presets_list.insertItem(current_row - 1, item)
            self.custom_presets_list.setCurrentItem(item)
            _save_presets_order()

    def _move_preset_down():
        current_row = self.custom_presets_list.currentRow()
        if current_row < self.custom_presets_list.count() - 1:
            item = self.custom_presets_list.takeItem(current_row)
            self.custom_presets_list.insertItem(current_row + 1, item)
            self.custom_presets_list.setCurrentItem(item)
            _save_presets_order()

    def _save_presets_order():
        order = []
        for i in range(self.custom_presets_list.count()):
            item = self.custom_presets_list.item(i)
            if isinstance(item, CustomPresetListItem):
                order.append(item.preset_id)
        self.event_bus.emit(Events.ApiPresets.SAVE_PRESETS_ORDER, {'order': order})
    def _on_custom_preset_selection_changed():
        if self.is_loading_preset:
            return  # Пропускаем обработку во время загрузки, чтобы избежать множественных вопросов
        
        current_item = self.custom_presets_list.currentItem()
        
        if self.current_preset_id and self.current_preset_id in self.custom_presets_list_items:
            old_item = self.custom_presets_list_items[self.current_preset_id]
            if old_item.has_changes:
                reply = QMessageBox.question(self, _("Несохраненные изменения", "Unsaved changes"),
                                            _("Сохранить изменения?", "Save changes?"),
                                            QMessageBox.StandardButton.Yes | 
                                            QMessageBox.StandardButton.No | 
                                            QMessageBox.StandardButton.Cancel)
                
                if reply == QMessageBox.StandardButton.Cancel:
                    self.custom_presets_list.setCurrentItem(old_item)
                    return
                elif reply == QMessageBox.StandardButton.Yes:
                    _save_preset()
        
        if current_item and isinstance(current_item, CustomPresetListItem):
            self.remove_preset_btn.setEnabled(True)
            self.move_up_btn.setEnabled(self.custom_presets_list.currentRow() > 0)
            self.move_down_btn.setEnabled(self.custom_presets_list.currentRow() < self.custom_presets_list.count() - 1)
            _load_preset(current_item.preset_id)
            if self.api_settings_container:
                self.api_settings_container.setVisible(True)
        else:
            self.remove_preset_btn.setEnabled(False)
            self.move_up_btn.setEnabled(False)
            self.move_down_btn.setEnabled(False)
            if self.api_settings_container:
                self.api_settings_container.setVisible(False)

    def _select_custom_preset(preset_id):
        for i in range(self.custom_presets_list.count()):
            item = self.custom_presets_list.item(i)
            if isinstance(item, CustomPresetListItem) and item.preset_id == preset_id:
                self.custom_presets_list.setCurrentItem(item)
                break

    def _export_preset():
        if self.current_preset_id:
            path, _ = QFileDialog.getSaveFileName(self, _("Экспорт пресета", "Export preset"),
                                                   f"preset_{self.current_preset_id}.json",
                                                   "JSON Files (*.json)")
            if path:
                self.event_bus.emit(Events.ApiPresets.EXPORT_PRESET, {
                    'id': self.current_preset_id,
                    'path': path
                })

    def _save_preset():
        # Проверяем, что это кастомный пресет
        if not self.current_preset_id or self.current_preset_id not in self.custom_presets_list_items:
            return
        
        data = self.current_preset_data.copy()
        data['url'] = self.api_url_entry.text()
        data['default_model'] = self.api_model_entry.text()
        data['key'] = self.api_key_entry.text()
        data['known_models'] = self.current_preset_data.get('known_models', [])
        
        if self.template_combo.currentData():
            data['base'] = self.template_combo.currentData()
        else:
            data['base'] = None
        
        new_id = self.event_bus.emit_and_wait(Events.ApiPresets.SAVE_CUSTOM_PRESET, {'data': data}, timeout=1.0)
        
        if new_id and new_id[0]:
            self.original_preset_state = _get_current_state()
            _check_changes()
            
            if self.current_preset_id in self.custom_presets_list_items:
                item = self.custom_presets_list_items[self.current_preset_id]
                item.update_changes_indicator(False)
        
        return new_id[0] if new_id else None
    
    def _test_connection():
        if self.current_preset_data and self.current_preset_data.get('test_url'):
            self.test_button.setEnabled(False)
            self.test_button.setText(_("Тестирование...", "Testing..."))
            logger.info(f"Initiating test connection for preset {self.current_preset_id}")
            self.event_bus.emit(Events.ApiPresets.TEST_CONNECTION, {
                'id': self.current_preset_id,
                'key': self.api_key_entry.text()
            })
    
    def _toggle_key_visibility():
        if self.api_key_entry.echoMode() == QLineEdit.EchoMode.Password:
            self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Normal)
            self.key_visibility_button.setIcon(qta.icon('fa5s.eye-slash'))
        else:
            self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
            self.key_visibility_button.setIcon(qta.icon('fa5s.eye'))
    
    def _on_template_changed():
        if self.is_loading_preset:
            return
        
        template_id = self.template_combo.currentData()
        if not self.current_preset_id:
            return
        
        # БЕЗ ШАБЛОНА - разблокировать URL, скрыть help, показать стандартные поля, скрыть g4f-поля
        if template_id is None:
            self.api_url_entry.setEnabled(True)
            for label in [self.url_help_label, self.model_help_label, self.key_help_label]:
                label.setVisible(False)
            self.test_button.setVisible(False)
            
            # Показываем стандартные поля (как в старом коде)
            is_g4f = False
            for field in ['api_url_entry', 'api_model_entry', 'api_key_entry', 'nm_api_key_res_label']:
                frame = getattr(self, f"{field}_frame", None)
                if frame:
                    frame.setVisible(True)  # Всегда показываем для "Без шаблона"
            
            for field in ['g4f_version_entry', 'g4f_update_button']:
                frame = getattr(self, f"{field}_frame", None)
                if frame:
                    frame.setVisible(False)  # Скрываем g4f-поля
            
            if self.gemini_case_checkbox:
                frame = getattr(self, "gemini_case_checkbox_frame", None)
                if frame:
                    frame.setVisible(True)  # Показываем для "Без шаблона"
            
            self.current_preset_data['base'] = None
            self.current_preset_data['is_g4f'] = False
            self.current_preset_data['use_request'] = False
            self.current_preset_data['gemini_case'] = None
            self.current_preset_data['test_url'] = ''
            self.current_preset_data['url_tpl'] = ''
            self.current_preset_data['add_key'] = False
            self.current_preset_data['help_url'] = ''
            
            _check_changes()
            return
        
        # С ШАБЛОНОМ - заблокировать URL, применить настройки шаблона
        template_data = self.event_bus.emit_and_wait(Events.ApiPresets.GET_PRESET_FULL,
                                                    {'id': template_id}, timeout=1.0)
        if not template_data or not template_data[0]:
            return
        
        template = template_data[0]
        
        self.is_loading_preset = True
        
        # Собираем URL из шаблона с текущими значениями модели и ключа
        url_tpl = template.get('url_tpl', '')
        if url_tpl:
            # Используем текущую модель или дефолтную из шаблона
            current_model = self.api_model_entry.text()
            if not current_model:
                current_model = template.get('default_model', '')
                self.api_model_entry.setText(current_model)
            
            # Форматируем URL с моделью
            if '{model}' in url_tpl:
                url = url_tpl.format(model=current_model)
            else:
                url = url_tpl
            
            # Обработка ключа
            import re
            if template.get('add_key'):
                current_key = self.api_key_entry.text().strip()
                if current_key:
                    # Добавляем или обновляем ключ
                    if 'key=' not in url:
                        sep = '&' if '?' in url else '?'
                        url = f"{url}{sep}key={current_key}"
                    else:
                        # Заменяем существующее значение
                        url = re.sub(r'key=[^&]*', f'key={current_key}', url)
                else:
                    # Если ключ пустой, удаляем параметр key из URL, если он есть
                    url = re.sub(r'[?&]key=[^&]*', '', url)
                    # Удаляем возможный висячий ? или & в конце
                    url = url.rstrip('?&')
            
            self.api_url_entry.setText(url)
        else:
            # Если нет шаблона URL, используем обычный URL
            url = template.get('url', '')
            self.api_url_entry.setText(url)
        
        self.api_url_entry.setEnabled(False)  # БЛОКИРУЕМ при шаблоне
        
        is_g4f = template.get('is_g4f', False)
        
        # Логика видимости как в старом коде: скрываем/показываем поля
        for field in ['api_url_entry', 'api_key_entry', 'nm_api_key_res_label']:
            frame = getattr(self, f"{field}_frame", None)
            if frame:
                frame.setVisible(not is_g4f)
        
        # Поле модели всегда видно (как в старом коде для g4f)
        model_frame = getattr(self, "api_model_entry_frame", None)
        if model_frame:
            model_frame.setVisible(True)
        
        # Скрываем gemini_case для g4f (как в старом коде)
        if self.gemini_case_checkbox:
            frame = getattr(self, "gemini_case_checkbox_frame", None)
            if frame:
                frame.setVisible(template.get('gemini_case') is None and not is_g4f)
        
        # Показываем g4f-поля только для is_g4f
        for field in ['g4f_version_entry', 'g4f_update_button']:
            frame = getattr(self, f"{field}_frame", None)
            if frame:
                frame.setVisible(is_g4f)
        
        self.test_button.setVisible(bool(template.get('test_url')))
        
        if template.get('help_url'):
            for label in [self.url_help_label, self.model_help_label, self.key_help_label]:
                label.setVisible(True)
            base_help_url = template.get('help_url')
            self.url_help_label.setText(f'<a href="{base_help_url}">{_("Документация", "Documentation")}</a>')
            self.model_help_label.setText(f'<a href="{base_help_url}">{_("Список моделей", "Models list")}</a>')
            self.key_help_label.setText(f'<a href="{base_help_url}">{_("Получить ключ", "Get API key")}</a>')
        else:
            for label in [self.url_help_label, self.model_help_label, self.key_help_label]:
                label.setVisible(False)
        
        known_models = template.get('known_models', [])
        if known_models:
            self.api_model_list_model.setStringList(known_models)
        
        self.current_preset_data['base'] = template_id
        self.current_preset_data['is_g4f'] = is_g4f
        self.current_preset_data['use_request'] = template.get('use_request', False)
        self.current_preset_data['gemini_case'] = template.get('gemini_case')
        self.current_preset_data['test_url'] = template.get('test_url', '')
        self.current_preset_data['url_tpl'] = template.get('url_tpl', '')
        self.current_preset_data['add_key'] = template.get('add_key', False)
        self.current_preset_data['help_url'] = template.get('help_url', '')
        
        self.is_loading_preset = False
        _check_changes()

    def _cancel_changes():
        """Отменить все несохраненные изменения"""
        if not self.current_preset_id or not self.original_preset_state:
            return
        
        self.is_loading_preset = True
        
        # Восстанавливаем оригинальные значения
        self.api_url_entry.setText(self.original_preset_state.get('url', ''))
        self.api_model_entry.setText(self.original_preset_state.get('model', ''))
        self.api_key_entry.setText(self.original_preset_state.get('key', ''))
        
        # Восстанавливаем шаблон
        original_base = self.original_preset_state.get('base')
        if original_base:
            for i in range(self.template_combo.count()):
                if self.template_combo.itemData(i) == original_base:
                    self.template_combo.setCurrentIndex(i)
                    break
        else:
            self.template_combo.setCurrentIndex(0)
        
        self.is_loading_preset = False
        
        # Сбрасываем индикаторы изменений
        _check_changes()
        
        # Обновляем элемент в списке
        if self.current_preset_id in self.custom_presets_list_items:
            item = self.custom_presets_list_items[self.current_preset_id]
            item.update_changes_indicator(False)

    def _load_preset(preset_id):
        self.is_loading_preset = True
        
        preset_data = self.event_bus.emit_and_wait(Events.ApiPresets.GET_PRESET_FULL, 
                                                    {'id': preset_id}, timeout=1.0)
        if not preset_data or not preset_data[0]:
            self.is_loading_preset = False
            return
        
        preset = preset_data[0]
        self.current_preset_data = preset
        self.current_preset_id = preset_id
        
        # Определяем, является ли пресет кастомным
        is_custom = preset_id in self.custom_presets_list_items
        
        state = self.event_bus.emit_and_wait(Events.ApiPresets.LOAD_PRESET_STATE,
                                            {'id': preset_id}, timeout=1.0)
        state = state[0] if state and state[0] else {}
        
        # Предпочитаем state over preset для всех полей
        url = state.get('url', preset.get('url', ''))
        model = state.get('model', preset.get('default_model', ''))
        key = state.get('key', preset.get('key', ''))
        
        self.api_url_entry.setText(url)
        self.api_model_entry.setText(model)
        self.api_key_entry.setText(key)
        
        if self.gemini_case_checkbox and preset.get('gemini_case') is None:
            self.gemini_case_checkbox.setChecked(state.get('gemini_case', False))
        
        # Устанавливаем шаблон
        base = preset.get('base')
        if base:
            for i in range(self.template_combo.count()):
                if self.template_combo.itemData(i) == base:
                    self.template_combo.setCurrentIndex(i)
                    break
        else:
            self.template_combo.setCurrentIndex(0)
        
        is_g4f = preset.get('is_g4f', False)
        
        # URL разблокирован только если кастомный И НЕТ шаблона
        has_template = base is not None
        self.api_url_entry.setEnabled(is_custom and not is_g4f and not has_template)
        self.api_model_entry.setEnabled(True)
        self.api_key_entry.setEnabled(not is_g4f)
        
        for field in ['api_url_entry', 'api_model_entry', 'api_key_entry', 'nm_api_key_res_label']:
            frame = getattr(self, f"{field}_frame", None)
            if frame:
                frame.setVisible(not is_g4f)
        
        for field in ['g4f_version_entry', 'g4f_update_button']:
            frame = getattr(self, f"{field}_frame", None)
            if frame:
                frame.setVisible(is_g4f)
        
        if self.gemini_case_checkbox:
            frame = getattr(self, "gemini_case_checkbox_frame", None)
            if frame:
                frame.setVisible(preset.get('gemini_case') is None)
        
        self.test_button.setVisible(bool(preset.get('test_url')))
        
        self.provider_label.setText(preset.get('name', ''))
        
        if preset.get('help_url'):
            for label in [self.url_help_label, self.model_help_label, self.key_help_label]:
                label.setVisible(True)
            base_help_url = preset.get('help_url')
            self.url_help_label.setText(f'<a href="{base_help_url}">{_("Документация", "Documentation")}</a>')
            self.model_help_label.setText(f'<a href="{base_help_url}">{_("Список моделей", "Models list")}</a>')
            self.key_help_label.setText(f'<a href="{base_help_url}">{_("Получить ключ", "Get API key")}</a>')
        else:
            for label in [self.url_help_label, self.model_help_label, self.key_help_label]:
                label.setVisible(False)
        
        known_models = preset.get('known_models', [])
        if known_models:
            self.api_model_list_model.setStringList(known_models)
        
        _apply_settings_from_preset(preset)
        
        self.settings.set("LAST_API_PRESET_ID", preset_id)
        self.settings.save_settings()
        
        # Устанавливаем original_state ПОСЛЕ всех setText/setIndex/setChecked
        self.original_preset_state = _get_current_state()
        
        # Показываем кнопку сохранения только для кастомных пресетов
        self.save_preset_button.setVisible(is_custom)
        self.save_preset_button.setEnabled(False)  # Изначально отключена
        
        self.is_loading_preset = False
        _check_changes()  # Проверяем изменения в конце загрузки

    def _get_current_state():
        state = {
            'url': self.api_url_entry.text(),
            'model': self.api_model_entry.text(),
            'key': self.api_key_entry.text(),
            'base': self.template_combo.currentData()
        }
        # Включаем gemini_case если он редактируемый (None в пресете)
        if self.gemini_case_checkbox and self.current_preset_data.get('gemini_case') is None:
            state['gemini_case'] = self.gemini_case_checkbox.isChecked()
        return state
    
    def _check_changes():
        # Проверяем, является ли текущий пресет кастомным
        if not self.current_preset_id or self.current_preset_id not in self.custom_presets_list_items:
            return
        
        current_state = _get_current_state()
        has_changes = current_state != self.original_preset_state
        
        # Обновляем индикатор изменений в списке (только если изменилось)
        if self.current_preset_id in self.custom_presets_list_items:
            item = self.custom_presets_list_items[self.current_preset_id]
            if item.has_changes != has_changes:
                item.update_changes_indicator(has_changes)
        
        # Обновляем метку URL с индикатором изменений
        if hasattr(self, 'api_url_entry_frame'):
            url_layout = self.api_url_entry_frame.layout()
            if url_layout and url_layout.count() > 1:
                h_layout = url_layout.itemAt(1).layout()
                if h_layout:
                    for i in range(h_layout.count()):
                        widget = h_layout.itemAt(i).widget()
                        if isinstance(widget, QLabel) and not widget.openExternalLinks():
                            url_changed = current_state['url'] != self.original_preset_state.get('url', '')
                            if url_changed:
                                widget.setText(_('Ссылка API*', 'API URL*'))
                                widget.setStyleSheet("color: #f39c12; font-weight: bold;")
                            else:
                                widget.setText(_('Ссылка API', 'API URL'))
                                widget.setStyleSheet("")
                            break
        
        # Обновляем метку Model с индикатором изменений
        if hasattr(self, 'api_model_entry_frame'):
            model_layout = self.api_model_entry_frame.layout()
            if model_layout and model_layout.count() > 1:
                h_layout = model_layout.itemAt(1).layout()
                if h_layout:
                    for i in range(h_layout.count()):
                        widget = h_layout.itemAt(i).widget()
                        if isinstance(widget, QLabel) and not widget.openExternalLinks():
                            model_changed = current_state['model'] != self.original_preset_state.get('model', '')
                            if model_changed:
                                widget.setText(_('Модель*', 'Model*'))
                                widget.setStyleSheet("color: #f39c12; font-weight: bold;")
                            else:
                                widget.setText(_('Модель', 'Model'))
                                widget.setStyleSheet("")
                            break
        
        # Обновляем метку Key с индикатором изменений
        if hasattr(self, 'api_key_entry_frame'):
            key_layout = self.api_key_entry_frame.layout()
            if key_layout and key_layout.count() > 1:
                h_layout = key_layout.itemAt(1).layout()
                if h_layout:
                    for i in range(h_layout.count()):
                        widget = h_layout.itemAt(i).widget()
                        if isinstance(widget, QLabel) and not widget.openExternalLinks():
                            key_changed = current_state['key'] != self.original_preset_state.get('key', '')
                            if key_changed:
                                widget.setText(_('API Ключ*', 'API Key*'))
                                widget.setStyleSheet("color: #f39c12; font-weight: bold;")
                            else:
                                widget.setText(_('API Ключ', 'API Key'))
                                widget.setStyleSheet("")
                            break
        
        # Обновляем состояние кнопок
        self.save_preset_button.setEnabled(has_changes)
        self.save_preset_button.setVisible(True)  # Всегда показываем для кастомных пресетов
        self.cancel_button.setVisible(has_changes)  # Показываем кнопку Отменить только при наличии изменений
        
        if has_changes:
            # Зеленая кнопка Сохранить при наличии изменений
            self.save_preset_button.setStyleSheet("""
                QPushButton {
                    background-color: #27ae60;
                    color: white;
                    font-weight: bold;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background-color: #229954;
                }
                QPushButton:pressed {
                    background-color: #1e8449;
                }
            """)
        else:
            # Серая кнопка при отсутствии изменений
            self.save_preset_button.setStyleSheet("""
                QPushButton {
                    background-color: #95a5a6;
                    color: #ecf0f1;
                    font-weight: normal;
                    border: none;
                    padding: 8px;
                    border-radius: 4px;
                }
                QPushButton:disabled {
                    background-color: #7f8c8d;
                    color: #bdc3c7;
                }
            """)

    def _on_field_changed():
        if self.is_loading_preset:
            return
        
        # ВСЕГДА вызываем проверку изменений при изменении любого поля
        _check_changes()
        
        # Обновление URL при изменении модели/ключа (если URL заблокирован)
        if self.current_preset_data and not self.api_url_entry.isEnabled():
            url_tpl = self.current_preset_data.get('url_tpl')
            if url_tpl:
                model = self.api_model_entry.text()
                url = url_tpl.format(model=model) if '{model}' in url_tpl else url_tpl
                
                if self.current_preset_data.get('add_key'):
                    key = self.api_key_entry.text().strip()
                    import re
                    if key:
                        # Добавляем или обновляем ключ
                        if 'key=' not in url:
                            sep = '&' if '?' in url else '?'
                            url = f"{url}{sep}key={key}"
                        else:
                            url = re.sub(r'key=[^&]*', f'key={key}', url)
                    else:
                        # Если ключ пустой, удаляем параметр key из URL
                        url = re.sub(r'[?&]key=[^&]*', '', url)
                        # Удаляем возможный висячий ? или & в конце
                        url = url.rstrip('?&')
                
                self.is_loading_preset = True
                self.api_url_entry.setText(url)
                self.is_loading_preset = False
                # Снова проверяем после обновления URL
                _check_changes()

    def _load_presets():
        presets_meta = self.event_bus.emit_and_wait(Events.ApiPresets.GET_PRESET_LIST, timeout=1.0)
        if not presets_meta or not presets_meta[0]:
            return
        
        presets_meta = presets_meta[0]
        
        # Сохраняем список builtin пресетов для проверки
        self.builtin_preset_ids = set()
        builtin_presets = presets_meta.get('builtin', [])
        for preset in builtin_presets:
            self.builtin_preset_ids.add(preset.id)
        
        self.provider_delegate.set_presets_meta(builtin_presets + presets_meta.get('custom', []))
        
        self.template_combo.clear()
        self.template_combo.addItem(_("Без шаблона", "No template"), None)
        
        current_changes = {}
        for preset_id, item in self.custom_presets_list_items.items():
            if item.has_changes:
                current_changes[preset_id] = True
        
        # Очищаем список с блокировкой сигналов (если не заблокированы уже)
        self.custom_presets_list.blockSignals(True)
        self.custom_presets_list.clear()
        self.custom_presets_list_items.clear()
        self.custom_presets_list.blockSignals(False)
        
        custom_presets = presets_meta.get('custom', [])
        
        for preset in builtin_presets:
            self.template_combo.addItem(preset.name, preset.id)
        
        for preset in custom_presets:
            has_changes = current_changes.get(preset.id, False)
            item = CustomPresetListItem(preset.id, preset.name, has_changes)
            self.custom_presets_list.addItem(item)
            self.custom_presets_list_items[preset.id] = item
            logger.info(f"Added custom preset to list: {preset.name} (ID: {preset.id})")
        
        saved_id = self.settings.get("LAST_API_PRESET_ID", 0)
        if saved_id and saved_id in self.custom_presets_list_items:
            _select_custom_preset(saved_id)
        elif self.custom_presets_list.count() == 0:
            if self.api_settings_container:
                self.api_settings_container.setVisible(False)

    def _save_current_state():
        if self.current_preset_id and self.current_preset_id > 0:
            state = {
                'url': self.api_url_entry.text(),
                'model': self.api_model_entry.text(),
                'key': self.api_key_entry.text()
            }
            
            if self.gemini_case_checkbox and self.current_preset_data.get('gemini_case') is None:
                state['gemini_case'] = self.gemini_case_checkbox.isChecked()
            
            self.event_bus.emit(Events.ApiPresets.SAVE_PRESET_STATE, {
                'id': self.current_preset_id,
                'state': state
            })
    
    def _build_url(preset):
        url_tpl = preset.get('url_tpl') or preset.get('url', '')
        model = preset.get('default_model', '')
        
        if '{model}' in url_tpl:
            url = url_tpl.format(model=model)
        else:
            url = url_tpl
        
        if preset.get('add_key'):
            sep = '&' if '?' in url else '?'
            url = f"{url}{sep}key="
        
        return url
    
    def _apply_settings_from_preset(preset):
        self._save_setting("NM_API_URL", self.api_url_entry.text())
        self._save_setting("NM_API_MODEL", self.api_model_entry.text())
        self._save_setting("NM_API_KEY", self.api_key_entry.text())
        
        if preset.get('is_g4f'):
            self._save_setting("gpt4free", True)
            self._save_setting("gpt4free_model", self.api_model_entry.text())
        else:
            self._save_setting("gpt4free", False)
            self._save_setting("NM_API_REQ", preset.get('use_request', False))
            
            if preset.get('gemini_case') is not None:
                self._save_setting("GEMINI_CASE", preset.get('gemini_case'))
            elif self.gemini_case_checkbox:
                self._save_setting("GEMINI_CASE", self.gemini_case_checkbox.isChecked())
    
    def _on_key_changed():
        if self.is_loading_preset:
            return
        
        _save_current_state()
        
        # Проверяем изменения СРАЗУ при изменении ключа
        _check_changes()
        
        # Обновляем URL если нужно
        if self.current_preset_data and self.current_preset_data.get('add_key'):
            _on_field_changed()
    
    def _on_gemini_case_changed():
        if self.is_loading_preset:
            return
        
        if self.current_preset_id and self.current_preset_data.get('gemini_case') is None:
            self.event_bus.emit(Events.ApiPresets.SET_GEMINI_CASE, {
                'id': self.current_preset_id,
                'value': self.gemini_case_checkbox.isChecked()
            })
    
    def _on_test_result(event):
        data = event.data
        if data.get('id') != self.current_preset_id:
            return
        
        logger.info(f"Received test result in UI for {self.current_preset_id}: {data}")
        
        self.test_result_received.emit(data)

    def _process_test_result(data):
        self.test_button.setEnabled(True)
        self.test_button.setText(_("Тест подключения", "Test connection"))
        
        logger.info(f"Handling test result in UI: success={data.get('success')}, message={data.get('message')}")
        
        if data.get('success'):
            QMessageBox.information(self, _("Успех", "Success"), data.get('message', 'OK'))
            
            models = data.get('models', [])
            if models:
                self.event_bus.emit(Events.ApiPresets.UPDATE_PRESET_MODELS, {
                    'id': self.current_preset_id,
                    'models': models
                })
                logger.info(f"Emitted update models for preset {self.current_preset_id}")
                
                preset_data = self.event_bus.emit_and_wait(Events.ApiPresets.GET_PRESET_FULL, 
                                                        {'id': self.current_preset_id}, timeout=1.0)
                if preset_data and preset_data[0]:
                    preset = preset_data[0]
                    known_models = preset.get('known_models', [])
                    self.api_model_list_model.setStringList(known_models)
                    logger.info(f"Reloaded and updated completer with {len(known_models)} models for preset {self.current_preset_id}")
                else:
                    logger.warning(f"Failed to reload preset {self.current_preset_id} after test")
        else:
            QMessageBox.warning(self, _("Ошибка", "Error"), data.get('message', 'Connection failed'))

    
    self.test_result_received.connect(_process_test_result)
    
    def _on_preset_saved(event):
        preset_id = event.data.get('id')
        if not preset_id:
            return
        
        # Перезагружаем список пресетов с блокировкой сигналов
        self.custom_presets_list.blockSignals(True)
        _load_presets()
        self.custom_presets_list.blockSignals(False)
        
        # Выбираем сохраненный пресет, если он кастомный (без триггера событий)
        if preset_id in self.custom_presets_list_items:
            _select_custom_preset(preset_id)
    
    def _on_preset_deleted(event):
        _load_presets()
        if self.custom_presets_list.count() > 0:
            self.custom_presets_list.setCurrentRow(0)
        else:
            if self.api_settings_container:
                self.api_settings_container.setVisible(False)
    
    # Главный контейнер
    main_container = QWidget()
    main_layout = QVBoxLayout(main_container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(5)
    
    # 1. Заголовок секции
    section_header = QLabel(_("Настройки API", "API Settings"))
    section_header.setObjectName('SectionTitle')
    section_header.setAlignment(Qt.AlignmentFlag.AlignCenter)
    section_header.setStyleSheet('''
        QLabel#SectionTitle {
            font-size: 14px;
            font-weight: bold;
            color: #ffffff;
            padding: 5px 0;
        }
    ''')
    main_layout.addWidget(section_header)
    
    # Разделитель
    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    separator.setFrameShadow(QFrame.Shadow.Sunken)
    separator.setStyleSheet('''
        QFrame {
            background-color: #4a4a4a;
            max-height: 2px;
            margin: 0 10px 10px 10px;
        }
    ''')
    main_layout.addWidget(separator)
    
    # 2. Панель со списком пресетов (прижата к верху)
    custom_presets_frame = QFrame()
    custom_presets_frame.setFrameStyle(QFrame.Shape.Box)
    custom_presets_frame.setStyleSheet("""
        QFrame {
            border: 1px solid #cccccc;
            border-radius: 2px;
            padding: 5px;
        }
    """)
    custom_presets_frame.setFixedHeight(150)
    
    presets_layout = QHBoxLayout(custom_presets_frame)
    presets_layout.setContentsMargins(5, 5, 5, 5)
    
    self.custom_presets_list = QListWidget()
    self.custom_presets_list.itemSelectionChanged.connect(_on_custom_preset_selection_changed)
    presets_layout.addWidget(self.custom_presets_list, 1)
    
    buttons_layout = QVBoxLayout()
    buttons_layout.setSpacing(2)
    
    button_style = """
        QPushButton {
            border: 1px solid #cccccc;
            border-radius: 2px;
            padding: 5px;
            background-color: #f0f0f0;
        }
        QPushButton:hover {
            background-color: #e0e0e0;
        }
        QPushButton:pressed {
            background-color: #d0d0d0;
        }
        QPushButton:disabled {
            background-color: #f5f5f5;
            color: #999999;
        }
    """
    
    self.add_preset_btn = QPushButton()
    self.add_preset_btn.setIcon(qta.icon('fa5s.plus', color='#27ae60'))
    self.add_preset_btn.setToolTip(_("Добавить пресет", "Add preset"))
    self.add_preset_btn.clicked.connect(_add_custom_preset)
    self.add_preset_btn.setFixedSize(30, 30)
    self.add_preset_btn.setStyleSheet(button_style)
    
    self.remove_preset_btn = QPushButton()
    self.remove_preset_btn.setIcon(qta.icon('fa5s.minus', color='#e74c3c'))
    self.remove_preset_btn.setToolTip(_("Удалить пресет", "Remove preset"))
    self.remove_preset_btn.clicked.connect(_remove_custom_preset)
    self.remove_preset_btn.setEnabled(False)
    self.remove_preset_btn.setFixedSize(30, 30)
    self.remove_preset_btn.setStyleSheet(button_style)
    
    self.move_up_btn = QPushButton()
    self.move_up_btn.setIcon(qta.icon('fa5s.arrow-up', color='#3498db'))
    self.move_up_btn.setToolTip(_("Переместить вверх", "Move up"))
    self.move_up_btn.clicked.connect(_move_preset_up)
    self.move_up_btn.setEnabled(False)
    self.move_up_btn.setFixedSize(30, 30)
    self.move_up_btn.setStyleSheet(button_style)
    
    self.move_down_btn = QPushButton()
    self.move_down_btn.setIcon(qta.icon('fa5s.arrow-down', color='#3498db'))
    self.move_down_btn.setToolTip(_("Переместить вниз", "Move down"))
    self.move_down_btn.clicked.connect(_move_preset_down)
    self.move_down_btn.setEnabled(False)
    self.move_down_btn.setFixedSize(30, 30)
    self.move_down_btn.setStyleSheet(button_style)
    
    buttons_layout.addWidget(self.add_preset_btn)
    buttons_layout.addWidget(self.remove_preset_btn)
    buttons_layout.addWidget(self.move_up_btn)
    buttons_layout.addWidget(self.move_down_btn)
    buttons_layout.addStretch()
    
    presets_layout.addLayout(buttons_layout)
    
    main_layout.addWidget(custom_presets_frame)
    
    # Контейнер для настроек (скрыт по умолчанию)
    self.api_settings_container = QWidget()
    api_container_layout = QVBoxLayout(self.api_settings_container)
    api_container_layout.setContentsMargins(0, 10, 0, 0)
    api_container_layout.setSpacing(5)
    
    # 3. Название пресета и экспорт
    provider_info_layout = QHBoxLayout()
    self.provider_label = QLabel("")
    self.provider_label.setStyleSheet("font-weight: bold; font-size: 12px;")
    provider_info_layout.addWidget(self.provider_label)
    provider_info_layout.addStretch()
    
    export_button = QPushButton(_("Экспорт", "Export"))
    export_button.setIcon(qta.icon('fa5s.file-export', color='#3498db'))
    export_button.clicked.connect(_export_preset)
    export_button.setMaximumWidth(100)
    provider_info_layout.addWidget(export_button)
    
    api_container_layout.addLayout(provider_info_layout)
    
    # 4. Комбобокс шаблона СРАЗУ под названием
    template_layout = QHBoxLayout()
    template_label = QLabel(_("Шаблон:", "Template:"))
    self.template_combo = QComboBox()
    self.template_combo.setMinimumWidth(200)
    self.template_combo.currentIndexChanged.connect(_on_template_changed)
    template_layout.addWidget(template_label)
    template_layout.addWidget(self.template_combo)
    template_layout.addStretch()
    api_container_layout.addLayout(template_layout)
    
    # Добавляем небольшой отступ перед полями
    api_container_layout.addSpacing(10)
    
    # Конфигурация полей
    config = [        
        {'label': _('Ссылка API', 'API URL'),
         'key': 'NM_API_URL', 'type': 'entry',
         'widget_name': 'api_url_entry'},
        
        {'label': _('Модель', 'Model'),
         'key': 'NM_API_MODEL', 'type': 'entry',
         'widget_name': 'api_model_entry'},
        
        {'label': _('API Ключ', 'API Key'),
         'key': 'NM_API_KEY', 'type': 'entry',
         'widget_name': 'api_key_entry',
         'hide': True},
        
        {'label': _('Модель Gemini', 'Gemini Model'),
         'key': 'GEMINI_CASE_UI', 'type': 'checkbutton',
         'widget_name': 'gemini_case_checkbox',
         'tooltip': _("Формат сообщений gemini отличается от других",
                      "Gemini message format differs from others")},
        
        {'label': _('Резервные ключи', 'Reserve keys'),
         'key': 'NM_API_KEY_RES', 'type': 'textarea',
         'hide': bool(self.settings.get("HIDE_PRIVATE")),
         'widget_name': 'nm_api_key_res_label'},
        
        {'label': _('Версия g4f', 'g4f version'),
         'key': 'G4F_VERSION', 'type': 'entry',
         'default': '0.4.7.7',
         'widget_name': 'g4f_version_entry',
         'tooltip': _('Версия g4f для установки', 'g4f version to install')},
        
        {'label': _('Обновить g4f', 'Update g4f'),
         'type': 'button',
         'command': self.trigger_g4f_reinstall_schedule,
         'widget_name': 'g4f_update_button',
         'icon': qta.icon('fa5s.download', color='#3498db')},
    ]
    
    from ui.gui_templates import create_settings_direct
    create_settings_direct(self, api_container_layout, config)
    
    # Получаем виджеты
    self.api_url_entry = getattr(self, 'api_url_entry')
    self.api_model_entry = getattr(self, 'api_model_entry')
    self.api_key_entry = getattr(self, 'api_key_entry')
    self.gemini_case_checkbox = getattr(self, 'gemini_case_checkbox', None)
    self.g4f_version_entry = getattr(self, 'g4f_version_entry', None)
    
    # Help labels
    self.url_help_label = QLabel()
    self.url_help_label.setOpenExternalLinks(True)
    self.url_help_label.setStyleSheet("color: #3498db;")
    
    self.model_help_label = QLabel()
    self.model_help_label.setOpenExternalLinks(True)
    self.model_help_label.setStyleSheet("color: #3498db;")
    
    self.key_help_label = QLabel()
    self.key_help_label.setOpenExternalLinks(True)
    self.key_help_label.setStyleSheet("color: #3498db;")
    
    def _reorganize_frame_layout(frame, help_label):
        if not hasattr(frame, 'layout') or not frame.layout():
            return
        
        old_layout = frame.layout()
        
        items = []
        while old_layout.count():
            item = old_layout.takeAt(0)
            if item.widget():
                items.append(item.widget())
        
        new_layout = QVBoxLayout()
        new_layout.setContentsMargins(0, 0, 0, 0)
        new_layout.setSpacing(2)
        
        new_layout.addWidget(help_label)
        
        horizontal_layout = QHBoxLayout()
        horizontal_layout.setContentsMargins(0, 0, 0, 0)
        for widget in items:
            horizontal_layout.addWidget(widget)
        
        new_layout.addLayout(horizontal_layout)
        
        QWidget().setLayout(old_layout)
        frame.setLayout(new_layout)

    if hasattr(self, 'api_url_entry_frame'):
        _reorganize_frame_layout(self.api_url_entry_frame, self.url_help_label)

    if hasattr(self, 'api_model_entry_frame'):
        _reorganize_frame_layout(self.api_model_entry_frame, self.model_help_label)

    if hasattr(self, 'api_key_entry_frame'):
        _reorganize_frame_layout(self.api_key_entry_frame, self.key_help_label)
    
    self.api_key_entry.setEchoMode(QLineEdit.EchoMode.Password)
    
    self.key_visibility_button = QToolButton()
    self.key_visibility_button.setIcon(qta.icon('fa5s.eye'))
    self.key_visibility_button.clicked.connect(_toggle_key_visibility)
    if hasattr(self, 'api_key_entry_frame'):
        key_layout = self.api_key_entry_frame.layout()
        if key_layout and key_layout.count() > 1:
            horizontal_layout = key_layout.itemAt(1).layout()
            if horizontal_layout:
                horizontal_layout.addWidget(self.key_visibility_button)
    
    # Кнопки: сначала Тест подключения
    test_button = QPushButton(_("Тест подключения", "Test connection"))
    test_button.setIcon(qta.icon('fa5s.satellite', color='#3498db'))
    test_button.clicked.connect(_test_connection)
    self.test_button = test_button
    
    buttons_layout = QHBoxLayout()
    buttons_layout.setSpacing(10)

    # Первая колонка - кнопка Отмена
    self.cancel_button = QPushButton(_("Отменить", "Cancel"))
    self.cancel_button.setIcon(qta.icon('fa5s.undo', color='#ffffff'))
    self.cancel_button.clicked.connect(_cancel_changes)
    self.cancel_button.setVisible(False)  # Скрыта по умолчанию
    self.cancel_button.setStyleSheet("""
        QPushButton {
            background-color: #e74c3c;
            color: white;
            font-weight: bold;
            border: none;
            padding: 8px;
            border-radius: 4px;
        }
        QPushButton:hover {
            background-color: #c0392b;
        }
        QPushButton:pressed {
            background-color: #a93226;
        }
        QPushButton:disabled {
            background-color: #ec7063;
            color: #f5b7b1;
        }
    """)

    # Вторая колонка - кнопка Сохранить
    self.save_preset_button = QPushButton(_("Сохранить", "Save"))
    self.save_preset_button.setIcon(qta.icon('fa5s.save', color='#ffffff'))
    self.save_preset_button.clicked.connect(_save_preset)
    self.save_preset_button.setVisible(False)
    self.save_preset_button.setStyleSheet("""
        QPushButton {
            background-color: #95a5a6;
            color: #ecf0f1;
            font-weight: normal;
            border: none;
            padding: 8px;
            border-radius: 4px;
        }
        QPushButton:disabled {
            background-color: #7f8c8d;
            color: #bdc3c7;
        }
    """)

    buttons_layout.addWidget(self.cancel_button, 1)
    buttons_layout.addWidget(self.save_preset_button, 1)

    # Кнопка Тест подключения - отдельно над кнопками
    test_button = QPushButton(_("Тест подключения", "Test connection"))
    test_button.setIcon(qta.icon('fa5s.satellite', color='#3498db'))
    test_button.clicked.connect(_test_connection)
    self.test_button = test_button

    api_container_layout.addWidget(self.test_button)
    api_container_layout.addLayout(buttons_layout)
    
    # Добавляем stretch в контейнер настроек
    api_container_layout.addStretch()
    
    main_layout.addWidget(self.api_settings_container)
    self.api_settings_container.setVisible(False)
    
    # Добавляем stretch в главный layout
    main_layout.addStretch()
    
    parent.layout().addWidget(main_container)
    
    self.api_model_completer = QCompleter()
    self.api_model_list_model = QStringListModel()
    self.api_model_completer.setModel(self.api_model_list_model)
    self.api_model_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    self.api_model_entry.setCompleter(self.api_model_completer)
    
    self.provider_delegate = ProviderDelegate(self.template_combo)
    self.template_combo.view().setItemDelegate(self.provider_delegate)
    
    self.api_model_entry.textChanged.connect(_on_field_changed)
    self.api_key_entry.textChanged.connect(_on_key_changed)
    self.api_url_entry.textChanged.connect(_on_field_changed)
    
    if self.gemini_case_checkbox:
        self.gemini_case_checkbox.stateChanged.connect(_on_gemini_case_changed)
    
    self.event_bus.subscribe(Events.ApiPresets.TEST_RESULT, _on_test_result, weak=False)
    self.event_bus.subscribe(Events.ApiPresets.PRESET_SAVED, _on_preset_saved, weak=False)
    self.event_bus.subscribe(Events.ApiPresets.PRESET_DELETED, _on_preset_deleted, weak=False)
    
    QTimer.singleShot(100, _load_presets)