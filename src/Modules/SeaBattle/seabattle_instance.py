# seabattle_instance.py

import re
import multiprocessing
from typing import Dict, Any, Optional

# Предполагается, что эти импорты находятся в корневом каталоге проекта
from main_logger import logger
from modules.game_interface import GameInterface

class SeaBattleGame(GameInterface):
    """Реализация игры в 'Морской бой' для взаимодействия с LLM."""

    def __init__(self, character, game_id: str = "seabattle"):
        super().__init__(character, game_id)
        self.gui_process: Optional[multiprocessing.Process] = None
        self.command_queue: Optional[multiprocessing.Queue] = None
        self.state_queue: Optional[multiprocessing.Queue] = None

    def start(self, params: Dict[str, Any]):
        if self.gui_process and self.gui_process.is_alive():
            logger.warning(f"[{self.character.char_id}] Процесс 'Морского боя' уже запущен. Останавливаем.")
            self.stop({})

        try:
            # Важно: seabattle_gui должен быть импортируем
            from modules.SeaBattle.seabattle_gui import run_seabattle_gui_process

            self.character.set_variable("playingGame", True)
            self.character.set_variable("game_id", self.game_id)

            self.command_queue = multiprocessing.Queue()
            self.state_queue = multiprocessing.Queue()

            logger.info(f"[{self.character.char_id}] Запуск GUI для 'Морского боя'.")

            self.gui_process = multiprocessing.Process(
                target=run_seabattle_gui_process,
                args=(self.command_queue, self.state_queue),
                daemon=True
            )
            self.gui_process.start()
        except ImportError as e:
            logger.error(f"[{self.character.char_id}] Не удалось импортировать модуль 'Морского боя': {e}", exc_info=True)
            self.cleanup()
        except Exception as e:
            logger.error(f"[{self.character.char_id}] Ошибка при запуске игры 'Морской бой': {e}", exc_info=True)
            self.cleanup()

    def _send_command(self, command_data: Dict[str, Any]):
        if self.character.get_variable("playingGame") and self.command_queue and self.gui_process and self.gui_process.is_alive():
            try:
                self.command_queue.put(command_data)
                logger.debug(f"[{self.character.char_id}] Отправлена команда в 'Морской бой': {command_data}")
            except Exception as e:
                logger.error(f"[{self.character.char_id}] Ошибка при отправке команды в очередь: {e}")
        else:
            logger.warning(f"[{self.character.char_id}] Невозможно отправить команду: игра неактивна.")

    def stop(self, params: Dict[str, Any]):
        logger.info(f"[{self.character.char_id}] Остановка игры 'Морской бой'.")
        self._send_command({"action": "stop_gui_process"})

        if self.gui_process and self.gui_process.is_alive():
            self.gui_process.join(timeout=5)
            if self.gui_process.is_alive():
                logger.warning(f"[{self.character.char_id}] Процесс GUI 'Морского боя' не завершился, принудительное завершение.")
                self.gui_process.terminate()
        
        self.cleanup()

    def cleanup(self):
        logger.debug(f"[{self.character.char_id}] Очистка ресурсов 'Морского боя'.")
        self.character.set_variable("playingGame", False)
        self.character.set_variable("game_id", None)
        
        if self.command_queue: self.command_queue.close()
        if self.state_queue: self.state_queue.close()

        self.gui_process = None
        self.command_queue = None
        self.state_queue = None

    def process_llm_tags(self, response: str) -> str:
        """Обрабатывает теги для управления игрой из ответа LLM."""
        
        # Тег для расстановки корабля: <PlaceShip>A1,4,H</PlaceShip> (Координата,Длина,Ориентация H/V)
        place_ship_match = re.search(r"<PlaceShip>(.*?)</PlaceShip>", response, re.IGNORECASE)
        if place_ship_match:
            spec = place_ship_match.group(1).strip()
            self._send_command({"action": "llm_place_ship", "spec": spec})
            logger.info(f"[{self.character.char_id}] LLM размещает корабль: {spec}.")
            response = response.replace(place_ship_match.group(0), "", 1).strip()

        # Тег для случайной расстановки оставшихся кораблей
        if "<PlaceShipsRandomly/>" in response:
            self._send_command({"action": "llm_place_randomly"})
            logger.info(f"[{self.character.char_id}] LLM запросил случайную расстановку своих кораблей.")
            response = response.replace("<PlaceShipsRandomly/>", "", 1).strip()

        # Тег для совершения хода: <MakeMove>B5</MakeMove>
        make_move_match = re.search(r"<MakeMove>([A-J][1-9]|A10|B10|C10|D10|E10|F10|G10|H10|I10|J10)</MakeMove>", response, re.IGNORECASE)
        if make_move_match:
            coord = make_move_match.group(1).strip().upper()
            self._send_command({"action": "llm_move", "coord": coord})
            logger.info(f"[{self.character.char_id}] LLM делает ход: {coord}.")
            response = response.replace(make_move_match.group(0), "", 1).strip()
            
        return response

    def get_state_prompt(self) -> Optional[str]:
        """
        Читает состояние из очереди, устанавливает переменные для DSL
        и обрабатывает файл seabattle.system.
        """
        if not self.state_queue:
            return None

        latest_state: Optional[Dict[str, Any]] = None
        # Забираем самое последнее состояние из очереди, отбрасывая промежуточные
        while not self.state_queue.empty():
            try:
                latest_state = self.state_queue.get_nowait()
            except Exception:
                break

        if not latest_state:
            # Если данных нет, запросим их у модуля игры
            self._send_command({"action": "get_state"})
            return "Игра 'Морской бой' активна. Ожидание данных от игрового модуля..."

        # --- Установка переменных для DSL на основе состояния ---
        llm_id = latest_state.get('llm_id')

        # 1. Основной статус игры
        self.character.set_variable("GAME_STATE_PHASE", latest_state.get('phase'))
        self.character.set_variable("GAME_STATE_IS_LLM_TURN", not latest_state.get('is_player_turn'))
        self.character.set_variable("GAME_STATE_IS_GAME_OVER", latest_state.get('phase') == 'game_over')

        winner_id = latest_state.get('winner')
        outcome = "Игра продолжается"
        if winner_id is not None:
            outcome = "Ты победил!" if winner_id == llm_id else "Ты проиграл."
        self.character.set_variable("GAME_STATE_OUTCOME", outcome)

        # 2. Доски (уже подготовленные для LLM в seabattle_logic.py)
        self.character.set_variable("GAME_STATE_MY_BOARD", latest_state.get('llm_my_board_str', 'Ошибка загрузки доски'))
        self.character.set_variable("GAME_STATE_OPPONENT_BOARD", latest_state.get('llm_opponent_view_str', 'Ошибка загрузки доски'))

        # 3. Информация для фазы расстановки
        ships_to_place = latest_state.get('llm_ships_to_place', [])
        self.character.set_variable("GAME_STATE_SHIPS_TO_PLACE_LIST", ", ".join(map(str, ships_to_place)))
        self.character.set_variable("GAME_STATE_HAS_SHIPS_TO_PLACE", bool(ships_to_place))

        # 4. Информация о последнем ходе
        last_move = latest_state.get('last_move')
        if last_move:
            self.character.set_variable("GAME_STATE_IS_LLM_LAST_MOVER", last_move['attacker'] == llm_id)
            self.character.set_variable("GAME_STATE_LAST_MOVE_COORD", last_move.get('coord_alg'))
            self.character.set_variable("GAME_STATE_LAST_MOVE_RESULT", last_move.get('result'))
        else:
            self.character.set_variable("GAME_STATE_IS_LLM_LAST_MOVER", False)
            self.character.set_variable("GAME_STATE_LAST_MOVE_COORD", None)
            self.character.set_variable("GAME_STATE_LAST_MOVE_RESULT", None)

        # 5. Новые тактические данные для умной игры
        hunt_info = latest_state.get('hunt_info', {})
        self.character.set_variable("GAME_STATE_HAS_WOUNDED_SHIPS", bool(hunt_info))
        self.character.set_variable("GAME_STATE_WOUNDED_SHIPS_INFO", hunt_info.get('wounded_info_str', ''))
        self.character.set_variable("GAME_STATE_HUNT_TARGETS_LIST", ", ".join(hunt_info.get('hunt_targets', [])))
        self.character.set_variable("GAME_STATE_SHOT_HISTORY_STRING", latest_state.get('shot_history_str', ''))

        # 6. Исполнение DSL-скрипта
        template_filename = f"{self.game_id}.system"
        try:
            logger.warning('ТУТ ТИПА НЕ ДОЛЖЕН ВЫЗЫВАТЬСЯ ЛИШНИЙ РАЗ СКРИПТ')
            prompt_content, _ = self.character.dsl_interpreter.execute_dsl_script(template_filename)
            logger.warning('ТУТ ТИПА НЕ ДОЛЖЕН ВЫЗЫВАТЬСЯ ЛИШНИЙ РАЗ СКРИПТ')
            return prompt_content
        except FileNotFoundError:
            logger.error(f"[{self.character.char_id}] Скрипт для игры '{self.game_id}' не найден: {template_filename}")
            return f"ОШИБКА: Не найден системный скрипт для игры '{self.game_id}'."
        except Exception as e:
            logger.error(f"[{self.character.char_id}] Ошибка исполнения DSL-скрипта '{template_filename}': {e}", exc_info=True)
            return f"ОШИБКА: Ошибка при генерации промпта для игры '{self.game_id}'."