from ui.gui_templates import create_settings_direct

def create_language_section(self, parent_layout):
    config = [
        {'label': 'Язык / Language', 'key': 'LANGUAGE', 'type': 'combobox',
         'options': ["RU", "EN"], 'default': "RU"},
        {'label': 'Перезапусти программу после смены!', 'type': 'text'},
        {'label': 'Restart program after change!', 'type': 'text'},
    ]

    create_settings_direct(self, parent_layout, config, 
                          title="Язык / Language")