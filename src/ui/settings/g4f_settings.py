from ui.gui_templates import create_settings_section
from utils import getTranslationVariant as _

def setup_g4f_controls(gui, parent_layout):
    g4f_config = [
        {'label': _('Использовать gpt4free', 'Use gpt4free'), 
         'key': 'gpt4free', 
         'type': 'checkbutton',
         'default_checkbutton': False},
        {'label': _('Модель gpt4free', 'model gpt4free'), 
         'key': 'gpt4free_model', 
         'type': 'entry', 
         'default': "gemini-1.5-flash"},
        {'label': _('Версия gpt4free', 'gpt4free Version'), 
         'key': 'G4F_VERSION',
         'type': 'entry',
         'default': '0.4.7.7',
         'widget_name': 'g4f_version_entry',
         'tooltip': _('Укажите версию g4f (например, 0.4.7.7 или latest). Обновление произойдет при следующем запуске.',
                      'Specify the g4f version (e.g., 0.4.7.7 or latest). The update will occur on the next launch.')},
        {'label': _('Запланировать обновление g4f', 'Schedule g4f Update'), 
         'type': 'button',
         'command': gui.trigger_g4f_reinstall_schedule}
    ]
    
    create_settings_section(gui, parent_layout, _("Настройки gpt4free", "gpt4free Settings"), g4f_config)