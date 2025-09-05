from PyQt6.QtCore import Qt

def wire_voiceover_settings_logic(self):
    """
    Подключает сигналы/слоты и вызывает первичную инициализацию.
    Ориентируемся на поведение оригинального файла.
    """

    # Локальная модель — выбор из комбобокса
    if hasattr(self, 'local_voice_combobox') and hasattr(self, 'on_local_voice_selected'):
        # activated (int) — как в оригинале
        self.local_voice_combobox.activated.connect(self.on_local_voice_selected)

    # Переключение TG/Local и видимости блоков при изменении метода/чекбокса
    if hasattr(self, 'method_combobox') and hasattr(self, 'switch_voiceover_settings'):
        self.method_combobox.currentTextChanged.connect(lambda _: self.switch_voiceover_settings())
    if hasattr(self, 'use_voice_checkbox') and hasattr(self, 'switch_voiceover_settings'):
        self.use_voice_checkbox.stateChanged.connect(lambda _: self.switch_voiceover_settings())

    # Первичная настройка (точно как делалось ранее)
    if hasattr(self, 'switch_voiceover_settings'):
        self.switch_voiceover_settings()
    if hasattr(self, 'check_triton_dependencies'):
        self.check_triton_dependencies()
    if hasattr(self, 'update_local_voice_combobox'):
        self.update_local_voice_combobox()