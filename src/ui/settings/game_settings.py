from ui.gui_templates import create_settings_section, create_section_header
from utils import getTranslationVariant as _

def setup_game_controls(self, parent):
    create_section_header(parent, _("Настройки игры", "Game Settings"))
    
    # Настройки диалогов и GameMaster
    dialogue_config = [
        {'label': _('Лимит речей нпс %', 'Limit NPC conversation'), 'key': 'CC_Limit_mod', 'type': 'entry',
         'default': 100, 'tooltip': _('Сколько от кол-ва персонажей может отклоняться повтор речей нпс',
                                      'How long NPC can talk ignoring player')},
        {'label': _('ГеймМастер - экспериментальная функция', 'GameMaster is experimental feature'),
         'type': 'text'},
        {'label': _('ГеймМастер включен', 'GameMaster is on'), 'key': 'GM_ON', 'type': 'checkbutton',
         'default_checkbutton': False, 'tooltip': 'Помогает вести диалоги, в теории устраняя проблемы'},
        {'label': _('Задача ГМу', 'GM task'), 'key': 'GM_SMALL_PROMPT', 'type': 'textarea', 'default': ""},
        {'label': _('ГеймМастер встревает каждые', 'GameMaster intervene each'), 'key': 'GM_REPEAT',
         'type': 'entry',
         'default': 2,
         'tooltip': _('Пример: 3 Означает, что через каждые две фразы ГМ напишет свое сообщение',
                      'Example: 3 means that after 2 phrases GM will write his message')},
    ]
    
    create_settings_section(
        self,
        parent,
        _("Настройки диалогов и GameMaster", "Dialogue and GameMaster Settings"),
        dialogue_config
    )
    
    # Настройки мода игры
    mod_config = [
        {'label': _('Меню выбора Мит', 'Mitas selection menu'), 'key': 'MITAS_MENU', 'type': 'checkbutton', 
         'default_checkbutton': False,
         'tooltip': _('Показывать меню выбора персонажей Мит в игре', 'Show Mitas character selection menu in game')},
        {'label': _('Меню эмоций Мит', 'Mitas emotion menu'), 'key': 'EMOTION_MENU', 'type': 'checkbutton', 
         'default_checkbutton': False,
         'tooltip': _('Показывать меню эмоций персонажей в игре', 'Show character emotion menu in game')},
        {'label': _('Игнорировать запросы из игры', 'Ignore timer'), 'key': 'IGNORE_GAME_REQUESTS', 'type': 'checkbutton',
         'default_checkbutton': False,
         'tooltip': _('Отключить запросы на генерацию из игры', 'Disable generation requests from the game')},
    ]
    
    create_settings_section(
        self,
        parent,
        _("Настройки мода", "Mod Settings"),
        mod_config
    )