# board_logic.py
import chess

class PureBoardLogic:
    def __init__(self):
        self.board = chess.Board()

    def reset_board(self, fen=None):
        """Сбрасывает доску в начальное состояние или в состояние по FEN."""
        if fen:
            try:
                self.board.set_fen(fen)
            except ValueError:
                print(f"Ошибка: Некорректный FEN: {fen}. Сброс на начальную позицию.")
                self.board.reset()
        else:
            self.board.reset()

    def get_fen(self):
        """Возвращает текущее состояние доски в формате FEN."""
        return self.board.fen()

    def get_turn(self):
        """Возвращает, чей сейчас ход (chess.WHITE или chess.BLACK)."""
        return self.board.turn

    def get_legal_moves_uci(self):
        """Возвращает список легальных ходов в формате UCI."""
        return [move.uci() for move in self.board.legal_moves]

    def make_move(self, uci_move_str):
        """
        Делает ход на доске, если он легален.
        uci_move_str: ход в формате UCI (e.g., "e2e4", "e7e8q").
        Возвращает: (True, "Ход сделан", san_move) если успешно, иначе (False, "Сообщение об ошибке", None).
        """
        try:
            move = chess.Move.from_uci(uci_move_str)
            if move in self.board.legal_moves:
                san_move_str = self.board.san(move) # Получаем SAN до хода
                self.board.push(move)
                return True, f"Ход {san_move_str} (UCI: {uci_move_str}) сделан.", san_move_str
            else:
                promotion_move_options = [
                    uci_move_str + 'q', uci_move_str + 'r', uci_move_str + 'b', uci_move_str + 'n'
                ]
                for promo_uci in promotion_move_options:
                    try:
                        promo_move = chess.Move.from_uci(promo_uci)
                        if promo_move in self.board.legal_moves:
                             return False, f"Нелегальный ход: {uci_move_str}. Возможно, вы имели в виду ход с превращением, например {promo_uci}?", None
                    except ValueError:
                        continue
                return False, f"Нелегальный ход: {uci_move_str}", None
        except ValueError:
            return False, f"Некорректный формат хода UCI: {uci_move_str}", None

    def is_game_over(self):
        """
        Проверяет, окончена ли игра.
        Возвращает: (True, "Сообщение о результате") если игра окончена, иначе (False, "Игра продолжается").
        """
        if self.board.is_checkmate():
            winner = "Черные" if self.board.turn == chess.WHITE else "Белые"
            return True, f"Мат! Победили {winner}."
        if self.board.is_stalemate():
            return True, "Ничья (пат)."
        if self.board.is_insufficient_material():
            return True, "Ничья (недостаточно материала)."
        if self.board.is_seventyfive_moves():
            return True, "Ничья (правило 75 ходов)."
        if self.board.is_fivefold_repetition():
            return True, "Ничья (пятикратное повторение позиции)."
        if self.board.can_claim_draw():
             return True, "Ничья (можно заявить по правилу 50 ходов или трехкратного повторения)."
        return False, "Игра продолжается."

    def get_piece_at(self, square_name):
        """Возвращает фигуру на указанной клетке (например, 'e4')."""
        try:
            square_index = chess.parse_square(square_name)
            return self.board.piece_at(square_index)
        except ValueError:
            return None

    def get_board_for_display(self):
        """
        Возвращает объект chess.Board для использования в GUI, если GUI
        умеет с ним работать напрямую для отрисовки.
        """
        return self.board