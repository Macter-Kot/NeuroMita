
from Modules.Chess.game_instance import ChessGame

from Modules.SeaBattle.seabattle_instance import SeaBattleGame
def get_available_games():
    available = {
        "chess": ChessGame,
        "seabattle": SeaBattleGame
    }
    return available