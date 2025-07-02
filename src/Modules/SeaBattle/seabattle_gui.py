# seabattle_gui.py

import sys
import multiprocessing
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QGridLayout, QPushButton, QGroupBox)
from PyQt6.QtGui import QPainter, QColor, QPen
from PyQt6.QtCore import Qt, pyqtSignal, QTimer

from Modules.SeaBattle.seabattle_logic import GameStateProvider, to_alg, from_alg

STYLESHEET = """
QWidget { background-color: #2E3440; color: #ECEFF4; font-family: Arial; }
QLabel#header { font-size: 24px; font-weight: bold; color: #88C0D0; padding: 10px; }
QLabel#info { font-size: 14px; color: #A3BE8C; }
QGroupBox { border: 1px solid #4C566A; border-radius: 5px; margin-top: 1ex; font-weight: bold; }
QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 3px; }
QPushButton { background-color: #5E81AC; border: none; padding: 8px; border-radius: 4px; font-weight: bold; }
QPushButton:hover { background-color: #81A1C1; }
QPushButton:disabled { background-color: #4C566A; color: #D8DEE9; }
"""

class BoardWidget(QWidget):
    cell_clicked = pyqtSignal(int, int, Qt.MouseButton)
    cell_hovered = pyqtSignal(int, int)

    COLORS = {
        0: QColor("#434C5E"), 1: QColor("#D8DEE9"), 2: QColor("#BF616A"), 
        3: QColor("#EBCB8B"), 4: QColor("#BF616A"), 5: QColor("#3B4252"),
        'opp_0': QColor("#ECEFF4"), 'opp_1': QColor("#BF616A"),
        'opp_2': QColor("#4C566A"), 'opp_3': QColor("#A3BE8C"),
    }

    def __init__(self, is_opponent_board=False):
        super().__init__()
        self.is_opponent_board = is_opponent_board
        self.board_data = [[0] * 10 for _ in range(10)]
        self.preview_ship = None
        self.setMouseTracking(True)
        self.setFixedSize(301, 301)

    def update_data(self, new_data):
        self.board_data = new_data
        self.update()

    def update_preview(self, ship_coords, is_valid):
        self.preview_ship = {'coords': ship_coords, 'is_valid': is_valid}
        self.update()

    def clear_preview(self):
        self.preview_ship = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        cell_size = 30
        for r, row in enumerate(self.board_data):
            for c, cell_state in enumerate(row):
                x, y = c * cell_size, r * cell_size
                key = f'opp_{cell_state}' if self.is_opponent_board else cell_state
                color = self.COLORS.get(key, QColor("black"))
                painter.fillRect(x, y, cell_size, cell_size, color)
                if not self.is_opponent_board and cell_state == 4:
                    painter.setPen(QPen(QColor("#A3BE8C"), 3))
                    painter.drawRect(x + 2, y + 2, cell_size - 4, cell_size - 4)
                painter.setPen(QColor("#2E3440"))
                painter.drawRect(x, y, cell_size, cell_size)
        if self.preview_ship:
            color = QColor(143, 188, 187, 180) if self.preview_ship['is_valid'] else QColor(191, 97, 106, 180)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            for c, r in self.preview_ship['coords']:
                painter.drawRect(c * cell_size, r * cell_size, cell_size, cell_size)

    def mouseMoveEvent(self, event):
        x, y = event.pos().x() // 30, event.pos().y() // 30
        if 0 <= x < 10 and 0 <= y < 10: self.cell_hovered.emit(x, y)
    
    def mousePressEvent(self, event):
        x, y = event.pos().x() // 30, event.pos().y() // 30
        if 0 <= x < 10 and 0 <= y < 10: self.cell_clicked.emit(x, y, event.button())

    def leaveEvent(self, event): self.clear_preview()

class SeaBattleWindow(QWidget):
    def __init__(self, command_queue, state_queue):
        super().__init__()
        self.command_queue = command_queue
        self.state_queue = state_queue
        self.game = GameStateProvider()
        
        self.ship_to_place = None
        self.init_ui()
        self.update_view()

        self.command_timer = QTimer(self)
        self.command_timer.timeout.connect(self.process_commands)
        self.command_timer.start(100) # Проверять очередь каждые 100 мс

    def init_ui(self):
        self.setWindowTitle("Морской Бой")
        self.setGeometry(100, 100, 620, 500)
        main_layout = QVBoxLayout(self)
        self.status_label = QLabel("Расстановка кораблей", objectName="header", alignment=Qt.AlignmentFlag.AlignCenter)
        self.info_label = QLabel("Выберите корабль", objectName="info", alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        main_layout.addWidget(self.info_label)

        boards_layout = QHBoxLayout()
        self.my_board_widget = BoardWidget()
        self.opponent_board_widget = BoardWidget(is_opponent_board=True)
        boards_layout.addWidget(self.my_board_widget)
        boards_layout.addWidget(self.opponent_board_widget)
        main_layout.addLayout(boards_layout)

        self.controls_group = QGroupBox("Ваши корабли")
        self.controls_layout = QGridLayout()
        self.controls_group.setLayout(self.controls_layout)
        main_layout.addWidget(self.controls_group)

        self.ship_buttons = {}
        ship_counts = {s: self.game.engine.SHIP_CONFIG.count(s) for s in sorted(list(set(self.game.engine.SHIP_CONFIG)), reverse=True)}
        for i, (length, count) in enumerate(ship_counts.items()):
            btn = QPushButton(f"{length}-палубный (x{count})")
            btn.clicked.connect(lambda _, l=length: self.select_ship_to_place(l))
            self.ship_buttons[length] = {'btn': btn, 'count': count}
            self.controls_layout.addWidget(btn, i // 2, i % 2)

        self.my_board_widget.cell_hovered.connect(self.on_my_board_hover)
        self.my_board_widget.cell_clicked.connect(self.on_my_board_click)
        self.opponent_board_widget.cell_clicked.connect(self.on_opponent_board_click)

    def send_state_update(self):
        """Отправляет текущее состояние игры в основной процесс."""
        state = self.game.get_full_state()
        try:
            self.state_queue.put(state)
        except Exception as e:
            print(f"GUI Error: Could not put state in queue: {e}")

    def process_commands(self):
        """Обрабатывает команды из основного процесса."""
        while not self.command_queue.empty():
            try:
                cmd = self.command_queue.get_nowait()
                action = cmd.get("action")

                if action == "stop_gui_process":
                    self.close()
                    return

                if action == "get_state":
                    self.send_state_update()
                    continue

                if action == "llm_place_ship":
                    spec = cmd.get("spec", "").split(',')
                    if len(spec) == 3:
                        try:
                            coord, length, orient_char = spec
                            x, y = from_alg(coord)
                            length = int(length)
                            orient = 'v' if orient_char.lower() == 'v' else 'h'
                            self.game.engine.place_ship(self.game.llm_id, x, y, length, orient)
                        except Exception as e:
                            print(f"LLM place ship error: {e}")
                
                if action == "llm_place_randomly":
                    self.game.engine.place_all_llm_ships_randomly()

                if action == "llm_move":
                    try:
                        x, y = from_alg(cmd.get("coord"))
                        self.game.engine.make_move(self.game.llm_id, x, y)
                    except Exception as e:
                        print(f"LLM move error: {e}")

                self.update_view()
                self.send_state_update()

            except multiprocessing.queues.Empty:
                break
            except Exception as e:
                print(f"GUI Error processing command: {e}")

    def select_ship_to_place(self, length):
        self.ship_to_place = {'len': length, 'orient': 'h'} if not (self.ship_to_place and self.ship_to_place['len'] == length) else None
        self.update_view()

    def on_my_board_hover(self, x, y):
        if self.game.engine.game_phase != "placement" or not self.ship_to_place: return
        l, o = self.ship_to_place['len'], self.ship_to_place['orient']
        coords = [(x + i, y) if o == 'h' else (x, y + i) for i in range(l)]
        is_valid = all(self.game.engine._is_valid_coord(px, py) for px, py in coords) and self.game.engine._can_place(self.game.player_id, coords)
        self.my_board_widget.update_preview(coords, is_valid)

    def on_my_board_click(self, x, y, button):
        state = self.game.get_full_state()
        if state['phase'] != "placement": return

        if button == Qt.MouseButton.RightButton and self.ship_to_place:
            self.ship_to_place['orient'] = 'v' if self.ship_to_place['orient'] == 'h' else 'h'
            self.on_my_board_hover(x, y)
            return
        
        if button == Qt.MouseButton.LeftButton and self.ship_to_place:
            l, o = self.ship_to_place['len'], self.ship_to_place['orient']
            success, msg = self.game.engine.place_ship(self.game.player_id, x, y, l, o)
            if success:
                self.ship_to_place = None
                self.update_view()
                self.send_state_update()
            else:
                self.info_label.setText(f"<font color='#BF616A'>{msg}</font>")

    def on_opponent_board_click(self, x, y, button):
        state = self.game.get_full_state()
        if state['phase'] != 'battle' or not state['is_player_turn']: return
        if button != Qt.MouseButton.LeftButton: return

        self.game.engine.make_move(self.game.player_id, x, y)
        self.update_view()
        self.send_state_update()

    def update_view(self):
        state = self.game.get_full_state()
        self.my_board_widget.update_data(state['player_board_raw'])
        self.opponent_board_widget.update_data(state['opponent_view_raw'])

        if state['phase'] == 'placement':
            self.controls_group.setVisible(True)
            self.opponent_board_widget.setVisible(False)
            ships_left = state['player_ships_to_place']
            for length, data in self.ship_buttons.items():
                count = ships_left.count(length)
                data['btn'].setText(f"{length}-палубный (x{count})")
                data['btn'].setEnabled(count > 0)
                is_selected = self.ship_to_place and self.ship_to_place['len'] == length
                data['btn'].setStyleSheet("background-color: #88C0D0;" if is_selected else "")

            if not ships_left:
                self.status_label.setText("Ожидание LLM")
                self.info_label.setText("Все ваши корабли расставлены.")
            else:
                self.status_label.setText("Расстановка кораблей")
                info = "Выберите корабль. ПКМ для вращения."
                if self.ship_to_place:
                    orient = "Вертикально" if self.ship_to_place['orient'] == 'v' else "Горизонтально"
                    info = f"Разместите {self.ship_to_place['len']}-палубный. ({orient})"
                self.info_label.setText(info)

        elif state['phase'] == 'battle':
            self.controls_group.setVisible(False)
            self.my_board_widget.clear_preview()
            self.opponent_board_widget.setVisible(True)
            self.status_label.setText("Ваш ход!" if state['is_player_turn'] else "Ход LLM")
            self.info_label.setText("Стреляйте по полю противника.")
            if state.get('last_move'):
                last_move = state['last_move']
                actor = "Вы" if last_move['attacker'] == self.game.player_id else "LLM"
                self.info_label.setText(f"Последний ход: {actor} на {last_move['coord_alg']} - {last_move['message']}")

        elif state['phase'] == 'game_over':
            self.controls_group.setVisible(False)
            self.my_board_widget.clear_preview()
            winner_text = "Вы победили!" if state['winner'] == self.game.player_id else "LLM победил."
            self.status_label.setText("Игра окончена")
            self.info_label.setText(winner_text)

def run_seabattle_gui_process(command_queue, state_queue):
    """Целевая функция для запуска GUI в отдельном процессе."""
    app = QApplication(sys.argv)
    app.setStyleSheet(STYLESHEET)
    window = SeaBattleWindow(command_queue, state_queue)
    window.show()
    # Отправить начальное состояние, как только GUI будет готов
    window.send_state_update()
    sys.exit(app.exec())