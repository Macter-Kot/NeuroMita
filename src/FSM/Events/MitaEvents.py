from enum import Enum

class MitaEvents(Enum):
    """События связанные с Митой"""
    PlayerTryToKillMita = "player_try_to_kill_mita"
    MitaKilledPlayer = "mita_killed_player"
    