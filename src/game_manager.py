from typing import Dict, Any, Optional, Type
from main_logger import logger
from modules.available_games import get_available_games
from modules.game_interface import GameInterface


class GameManager:
    """Управляет жизненным циклом и взаимодействием с экземплярами игр."""
    def __init__(self, character):
        self.character = character
        self.active_game: Optional[GameInterface] = None
        self.available_games: Dict[str, Type[GameInterface]] = get_available_games()

    def _parse_id_string(self, id_str: str) -> tuple[str, Dict[str, Any]]:
        parts = id_str.split('/')
        game_name = parts[0].lower()
        params = {}
        if len(parts) > 1:
            param_str = parts[1]
            # Простой случай: chess/easy или chess/resign
            if game_name == "chess":
                if param_str in self.available_games["chess"](self.character, "chess").elo_mapping:
                    params["difficulty"] = param_str
                elif param_str == "resign":
                    params["resign"] = True
        return game_name, params

    def start_game(self, full_id_str: str):
        if self.active_game:
            logger.warning(f"[{self.character.char_id}] Игра уже активна. Остановка перед запуском новой.")
            self.active_game.stop(params={})

        game_name, params = self._parse_id_string(full_id_str)
        
        game_class = self.available_games.get(game_name)
        if game_class:
            logger.info(f"[{self.character.char_id}] Запуск игры '{game_name}' с параметрами: {params}")
            self.active_game = game_class(self.character, game_name)
            self.active_game.start(params)
        else:
            logger.error(f"[{self.character.char_id}] Запрошена неизвестная игра: '{game_name}'")

    def stop_game(self, full_id_str: str):
        game_name, params = self._parse_id_string(full_id_str)

        if not self.active_game:
            logger.warning(f"[{self.character.char_id}] Получена команда остановки для '{game_name}', но нет активной игры.")
            return

        if self.active_game.game_id != game_name:
            logger.warning(f"[{self.character.char_id}] Получена команда остановки для '{game_name}', но активна игра '{self.active_game.game_id}'. Все равно останавливаем.")
        
        logger.info(f"[{self.character.char_id}] Остановка игры '{self.active_game.game_id}' с параметрами: {params}")
        self.active_game.stop(params)
        self.active_game = None

    def process_active_game_tags(self, response: str) -> str:
        if self.active_game:
            return self.active_game.process_llm_tags(response)
        return response
    
    def get_active_game_state_prompt(self) -> Optional[str]:
        """Делегирует получение промпта активной игре."""
        if self.active_game:
            return self.active_game.get_state_prompt()
        return None