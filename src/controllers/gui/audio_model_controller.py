
from main_logger import logger
from core.events import Events, Event
from .base_controller import BaseController
from ui.windows.voice_action_windows import VoiceInstallationWindow, VoiceActionWindow
from ui.windows.voice_action_windows import VCRedistWarningDialog, TritonDependenciesDialog
from utils import getTranslationVariant as _

from PyQt6.QtWidgets import (QApplication, QMessageBox)
from PyQt6.QtCore import QTimer, pyqtSignal, QThread, QEventLoop

class AudioModelController(BaseController):

    create_triton_dialog_signal = pyqtSignal(dict)
    create_vc_redist_dialog_signal = pyqtSignal(dict)
    show_vc_redist_dialog_signal = pyqtSignal()
    show_triton_dialog_signal = pyqtSignal(dict)

    def subscribe_to_events(self):
        self.event_bus.subscribe(Events.GUI.CHECK_TRITON_DEPENDENCIES, self._on_check_triton_dependencies, weak=False)
        self.event_bus.subscribe(Events.Audio.UPDATE_MODEL_LOADING_STATUS, self._on_update_model_loading_status, weak=False)
        self.event_bus.subscribe(Events.Audio.FINISH_MODEL_LOADING, self._on_finish_model_loading, weak=False)
        self.event_bus.subscribe(Events.Audio.CANCEL_MODEL_LOADING, self._on_cancel_model_loading, weak=False)
        self.event_bus.subscribe(Events.Audio.OPEN_VOICE_MODEL_SETTINGS_DIALOG, self._on_open_voice_model_settings_dialog, weak=False)
        self.event_bus.subscribe(Events.Audio.SHOW_VC_REDIST_DIALOG, self._on_show_vc_redist_dialog, weak=False)
        self.event_bus.subscribe(Events.Audio.SHOW_TRITON_DIALOG, self._on_show_triton_dialog, weak=False)
        self.event_bus.subscribe(Events.Audio.REFRESH_TRITON_STATUS, self._on_refresh_triton_status, weak=False)


    def _on_check_triton_dependencies(self, event: Event):
        if self.view and hasattr(self.view, 'check_triton_dependencies_signal') and self.view.check_triton_dependencies_signal:
            self.view.check_triton_dependencies_signal.emit()
        elif self.view and hasattr(self.view, 'check_triton_dependencies'):
            self.view.check_triton_dependencies()

    def _on_update_model_loading_status(self, event: Event):
        status = event.data.get('status', '')
        if self.view and hasattr(self.view, 'update_model_loading_status_signal') and self.view.update_model_loading_status_signal:
            self.view.update_model_loading_status_signal.emit(status)
        elif self.view and hasattr(self.view, 'loading_status_label'):
            QTimer.singleShot(0, lambda: self.view.loading_status_label.setText(status))

    def _on_finish_model_loading(self, event: Event):
        model_id = event.data.get('model_id')
        if self.view and hasattr(self.view, 'finish_model_loading_signal') and self.view.finish_model_loading_signal:
            self.view.finish_model_loading_signal.emit({'model_id': model_id})

    def _on_cancel_model_loading(self, event: Event):
        if self.view and hasattr(self.view, 'cancel_model_loading_signal') and self.view.cancel_model_loading_signal:
            self.view.cancel_model_loading_signal.emit()
        elif self.view and hasattr(self.view, 'cancel_model_loading') and hasattr(self.view, 'loading_dialog'):
            QTimer.singleShot(0, lambda: self.view.cancel_model_loading(self.view.loading_dialog))

    def _on_open_voice_model_settings_dialog(self, event: Event):
        """Обрабатывает запрос на открытие диалога настроек голосовых моделей"""
        try:
            from controllers.voice_model_controller import VoiceModelController
            from PyQt6.QtCore import QTimer
            
            # Получаем данные от AudioController
            audio_data = self.event_bus.emit_and_wait(Events.Audio.OPEN_VOICE_MODEL_SETTINGS, timeout=1.0)
            if not audio_data or not audio_data[0]:
                logger.error("Не удалось получить данные от AudioController")
                return
                
            voice_data = audio_data[0]
            local_voice = voice_data.get('local_voice')
            config_dir = voice_data.get('config_dir', 'Settings')
            settings = voice_data.get('settings')
            
            # Создаем callbacks
            def on_save_callback(settings_data):
                installed_models_ids = settings_data.get("installed_models", [])
                logger.info(f"Сохранены установленные модели: {installed_models_ids}")
                
                self.event_bus.emit(Events.Audio.REFRESH_VOICE_MODULES)
                
                if hasattr(self.view, 'update_local_voice_combobox'):
                    QTimer.singleShot(0, self.view.update_local_voice_combobox)
                
                current_model_id = settings.get("NM_CURRENT_VOICEOVER", None)
                if current_model_id and current_model_id not in installed_models_ids:
                    logger.warning(f"Текущая модель {current_model_id} была удалена.")
                    new_model_id = installed_models_ids[0] if installed_models_ids else None
                    settings.set("NM_CURRENT_VOICEOVER", new_model_id)
                    settings.save_settings()
                    self.main_controller.audio_controller.current_local_voice_id = new_model_id
                    
                    if hasattr(self.view, 'update_local_voice_combobox'):
                        QTimer.singleShot(0, self.view.update_local_voice_combobox)
            
            def check_installed_func(model_id):
                result = self.event_bus.emit_and_wait(
                    Events.Audio.CHECK_MODEL_INSTALLED,
                    {'model_id': model_id},
                    timeout=0.5
                )
                return result[0] if result else False
            
            def on_dialog_created(dialog):
                """Callback вызывается когда диалог создан в GUI потоке"""
                # Проверяем, есть ли уже контроллер
                if hasattr(self, '_voice_model_controller') and self._voice_model_controller:
                    # Обновляем данные в существующем контроллере
                    self._voice_model_controller.local_voice = local_voice
                    self._voice_model_controller.load_installed_models_state()
                    self._voice_model_controller.load_settings()
                    
                    # Проверяем, есть ли View в диалоге
                    if dialog.layout().count() == 0:
                        # View был потерян, пересоздаем
                        self._voice_model_controller.view_parent = dialog
                        self._voice_model_controller._create_view()
                    else:
                        # Обновляем данные в существующем View
                        if self._voice_model_controller.view:
                            self._voice_model_controller.view._initialize_data()
                else:
                    # Создаем новый контроллер
                    self._voice_model_controller = VoiceModelController(
                        view_parent=dialog,
                        config_dir=config_dir,
                        on_save_callback=on_save_callback,
                        local_voice=local_voice,
                        check_installed_func=check_installed_func
                    )
            
            def on_error(error_msg):
                logger.error(f"Ошибка создания диалога: {error_msg}")
                if hasattr(self.view, 'show_error_message'):
                    self.view.show_error_message(
                        _("Ошибка", "Error"),
                        _("Не удалось создать окно настроек.", "Failed to create settings window.")
                    )
            
            # Запрашиваем создание диалога через сигнал
            self.view.create_dialog_signal.emit({
                'callback': on_dialog_created,
                'error_callback': on_error
            })
            
        except Exception as e:
            logger.error(f"Ошибка при обработке запроса на открытие окна настроек: {e}", exc_info=True)

    def _on_show_vc_redist_dialog(self, event: Event):
        if not self.view:
            return 'close'

        result_holder = {'choice': 'close'}
        loop = QEventLoop()

        def _show_dialog():
            dialog = VCRedistWarningDialog(self.view.window())
            dialog.finished.connect(loop.quit)
            dialog.exec()
            result_holder['choice'] = dialog.get_choice()

        QTimer.singleShot(0, _show_dialog)
        loop.exec()

        return result_holder['choice']

    def _on_show_triton_dialog(self, event: Event):
        if not self.view:
            return 'skip'

        dependencies_status = event.data
        result_holder = {'choice': 'skip'}
        loop = QEventLoop()

        def _show_dialog():
            dialog = TritonDependenciesDialog(self.view.window(), dependencies_status)
            dialog.finished.connect(loop.quit)
            dialog.exec()
            result_holder['choice'] = dialog.get_choice()

        QTimer.singleShot(0, _show_dialog)
        loop.exec()

        return result_holder['choice']

    def _on_refresh_triton_status(self, event: Event):
        result = self.event_bus.emit_and_wait(Events.Audio.GET_TRITON_STATUS, timeout=1.0)
        return result[0] if result else None