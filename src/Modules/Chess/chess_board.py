# File: Modules/Chess/chess_board.py
import tkinter as tk
from tkinter import messagebox, simpledialog, font as tkFont
import chess # For chess.square, chess.Move
import multiprocessing
import queue # Для command_queue
import time # Для цикла обработки
import threading # Для блока __main__
import traceback # Added for error reporting

# Импортируем контроллер из соседнего файла
from .engine_handler import ChessGameController, MAIA_ELO as DEFAULT_MAIA_ELO # DEFAULT_MAIA_ELO если не передан ELO
from .board_logic import PureBoardLogic # Не используется напрямую здесь, но контроллер его использует

# --- Константы для GUI (остаются как были) ---
SQUARE_SIZE = 70
BOARD_BORDER_WIDTH = 2
DEFAULT_PIECE_FONT_SIZE = int(SQUARE_SIZE * 0.6)

class ChessGameModelTkStyles:
    COLOR_BOARD_LIGHT = "#EDE0C8"
    COLOR_BOARD_DARK = "#779556"
    COLOR_HIGHLIGHT_SELECTED = "#F5F57E"
    COLOR_HIGHLIGHT_POSSIBLE = "#A0D87E"
    COLOR_HIGHLIGHT_LAST_MOVE = "#FF8C8C"
    COLOR_BUTTON_BG = "#5C85D6"
    COLOR_BUTTON_HOVER_BG = "#4A6BAD"
    COLOR_BUTTON_PRESSED_BG = "#3A558C"
    COLOR_BUTTON_TEXT = "white"
    COLOR_WINDOW_BG = "#2E2E2E"
    COLOR_PANEL_BG = "#3C3C3C"
    COLOR_TEXT_LIGHT = "#E0E0E0"
    COLOR_BOARD_OUTER_BORDER = "#5F7745"
    PIECE_FONT_FAMILY = "DejaVu Sans"
    PIECE_FONT = (PIECE_FONT_FAMILY, DEFAULT_PIECE_FONT_SIZE, "bold")
    BUTTON_FONT = ("Arial", 11)
    STATUS_FONT = ("Arial", 9)
    COORDINATE_LABEL_FONT_TUPLE = ("Arial", 9, "bold") 
    COORDINATE_LABEL_FG = "#C0C0C0"
    COORDINATE_LABEL_BG = COLOR_WINDOW_BG
    LABEL_AREA_PADDING = 4

    @staticmethod
    def get_button_normal_style():
        return {
            "bg": ChessGameModelTkStyles.COLOR_BUTTON_BG, "fg": ChessGameModelTkStyles.COLOR_BUTTON_TEXT,
            "activebackground": ChessGameModelTkStyles.COLOR_BUTTON_PRESSED_BG,
            "activeforeground": ChessGameModelTkStyles.COLOR_BUTTON_TEXT,
            "relief": tk.FLAT, "font": ChessGameModelTkStyles.BUTTON_FONT, "padx": 10, "pady": 5
        }
    @staticmethod
    def get_button_hover_style(): return {"bg": ChessGameModelTkStyles.COLOR_BUTTON_HOVER_BG}

class ChessBoardCanvas(tk.Canvas):
    def __init__(self, parent, square_clicked_callback, **kwargs):
        super().__init__(parent, **kwargs)
        self.square_clicked_callback = square_clicked_callback
        self.bind("<Button-1>", self._on_mouse_press)
        self.config(
            width=8 * SQUARE_SIZE, height=8 * SQUARE_SIZE, bg=ChessGameModelTkStyles.COLOR_WINDOW_BG,
            highlightthickness=BOARD_BORDER_WIDTH, highlightbackground=ChessGameModelTkStyles.COLOR_BOARD_OUTER_BORDER
        )
    def _on_mouse_press(self, event):
        col_gui = event.x // SQUARE_SIZE
        row_gui = event.y // SQUARE_SIZE
        if 0 <= col_gui < 8 and 0 <= row_gui < 8:
            self.square_clicked_callback(row_gui, col_gui)

class PromotionDialog(simpledialog.Dialog):
    def __init__(self, parent, title, items_dict):
        self.items_dict = items_dict
        self.item_keys = list(items_dict.keys())
        self.result_value = None
        super().__init__(parent, title)
    def body(self, master):
        master.config(bg=ChessGameModelTkStyles.COLOR_PANEL_BG)
        tk.Label(master, text="Выберите фигуру:", bg=ChessGameModelTkStyles.COLOR_PANEL_BG, fg=ChessGameModelTkStyles.COLOR_TEXT_LIGHT).pack(pady=5)
        self.var = tk.StringVar(master)
        if self.item_keys: self.var.set(self.item_keys[0])
        first_rb = None
        for key_text in self.item_keys:
            rb = tk.Radiobutton(master, text=key_text, variable=self.var, value=key_text,
                                anchor=tk.W, indicatoron=True, bg=ChessGameModelTkStyles.COLOR_PANEL_BG,
                                fg=ChessGameModelTkStyles.COLOR_TEXT_LIGHT, selectcolor=ChessGameModelTkStyles.COLOR_WINDOW_BG,
                                activebackground=ChessGameModelTkStyles.COLOR_PANEL_BG, activeforeground=ChessGameModelTkStyles.COLOR_TEXT_LIGHT)
            rb.pack(fill=tk.X, padx=10)
            if first_rb is None: first_rb = rb
        return first_rb
    def buttonbox(self):
        box = tk.Frame(self, bg=ChessGameModelTkStyles.COLOR_PANEL_BG)
        w_ok = tk.Button(box, text="OK", width=10, command=self.ok, default=tk.ACTIVE)
        self._apply_button_style(w_ok)
        w_ok.pack(side=tk.LEFT, padx=5, pady=5)
        w_cancel = tk.Button(box, text="Отмена", width=10, command=self.cancel)
        self._apply_button_style(w_cancel)
        w_cancel.pack(side=tk.LEFT, padx=5, pady=5)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()
    def _apply_button_style(self, button):
        button.config(bg=ChessGameModelTkStyles.COLOR_BUTTON_BG, fg=ChessGameModelTkStyles.COLOR_BUTTON_TEXT,
                      activebackground=ChessGameModelTkStyles.COLOR_BUTTON_PRESSED_BG, activeforeground=ChessGameModelTkStyles.COLOR_BUTTON_TEXT,
                      relief=tk.FLAT, font=("Arial", 10))
        button.bind("<Enter>", lambda e, b=button: b.config(bg=ChessGameModelTkStyles.COLOR_BUTTON_HOVER_BG))
        button.bind("<Leave>", lambda e, b=button: b.config(bg=ChessGameModelTkStyles.COLOR_BUTTON_BG))
    def apply(self):
        selected_key = self.var.get()
        if selected_key and selected_key in self.items_dict: self.result_value = self.items_dict[selected_key]


class ChessGuiTkinter(tk.Tk):
    def __init__(self, game_controller: ChessGameController): 
        super().__init__()
        self.game_controller = game_controller
        self.title(f"Шахматы против Maia ELO {self.game_controller.current_maia_elo if self.game_controller else DEFAULT_MAIA_ELO}")
        self.configure(bg=ChessGameModelTkStyles.COLOR_WINDOW_BG)

        coord_font_tuple = ChessGameModelTkStyles.COORDINATE_LABEL_FONT_TUPLE
        # Ensure unique font name if this class is instantiated multiple times in the same Tk interpreter instance
        font_name_candidate = "NeuroMitaAppCoordFont"
        try:
            self.app_coord_font = tkFont.Font(name=font_name_candidate,
                                              family=coord_font_tuple[0],
                                              size=coord_font_tuple[1],
                                              weight=coord_font_tuple[2],
                                              exists=True) # Check if it exists
        except tk.TclError: # If it doesn't exist, tkFont.Font(..., exists=True) raises TclError
            self.app_coord_font = tkFont.Font(name=font_name_candidate,
                                              family=coord_font_tuple[0],
                                              size=coord_font_tuple[1],
                                              weight=coord_font_tuple[2])


        coord_label_strip_width_approx = self.app_coord_font.measure("W") + ChessGameModelTkStyles.LABEL_AREA_PADDING * 2 + 5
        coord_label_strip_height_approx = self.app_coord_font.metrics('linespace') + ChessGameModelTkStyles.LABEL_AREA_PADDING * 2 + 5
        
        min_width = int(8 * SQUARE_SIZE + 2 * BOARD_BORDER_WIDTH + 250 + 40 + coord_label_strip_width_approx)
        min_height = int(8 * SQUARE_SIZE + 2 * BOARD_BORDER_WIDTH + 60 + 40 + coord_label_strip_height_approx)
        self.minsize(min_width, min_height)

        self.piece_symbols = {
            'P': '♙', 'N': '♘', 'B': '♗', 'R': '♖', 'Q': '♕', 'K': '♔',
            'p': '♟', 'n': '♞', 'b': '♝', 'r': '♜', 'q': '♛', 'k': '♚'
        }
        self.selected_square_gui_coords = None
        self.possible_moves_for_selected_gui_coords = []
        self.last_move_squares_gui_coords = []
        self.square_bg_item_ids = [[None for _ in range(8)] for _ in range(8)]
        self.piece_item_ids = [[None for _ in range(8)] for _ in range(8)]
        self.square_original_colors = [[None for _ in range(8)] for _ in range(8)]
        self.rank_labels_gui = [None] * 8
        self.file_labels_gui = [None] * 8
        
        self.is_closing = False 

        self._init_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_closing_event)

    def _init_ui(self):
        main_layout_frame = tk.Frame(self, bg=ChessGameModelTkStyles.COLOR_WINDOW_BG)
        main_layout_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=20, pady=20)
        board_area_frame = tk.Frame(main_layout_frame, bg=ChessGameModelTkStyles.COLOR_WINDOW_BG)
        board_area_frame.pack(side=tk.LEFT, fill=tk.NONE, expand=False)
        
        _label_font_obj_for_ui = self.app_coord_font 
        _label_fg = ChessGameModelTkStyles.COORDINATE_LABEL_FG
        _label_bg = ChessGameModelTkStyles.COORDINATE_LABEL_BG
        _label_pad = ChessGameModelTkStyles.LABEL_AREA_PADDING

        rank_label_width = _label_font_obj_for_ui.measure("W") + _label_pad * 2
        file_label_height = _label_font_obj_for_ui.metrics('linespace') + _label_pad * 2
        
        board_area_frame.grid_columnconfigure(0, minsize=rank_label_width)
        board_area_frame.grid_rowconfigure(8, minsize=file_label_height)
        for r_gui in range(8):
            board_area_frame.grid_rowconfigure(r_gui, minsize=SQUARE_SIZE)
            lbl = tk.Label(board_area_frame, text="", font=_label_font_obj_for_ui, fg=_label_fg, bg=_label_bg)
            lbl.grid(row=r_gui, column=0, sticky=tk.NSEW)
            self.rank_labels_gui[r_gui] = lbl
        for c_gui in range(8):
            board_area_frame.grid_columnconfigure(c_gui + 1, minsize=SQUARE_SIZE)
            lbl = tk.Label(board_area_frame, text="", font=_label_font_obj_for_ui, fg=_label_fg, bg=_label_bg)
            lbl.grid(row=8, column=c_gui + 1, sticky=tk.NSEW)
            self.file_labels_gui[c_gui] = lbl
        corner_lbl = tk.Label(board_area_frame, text="", bg=_label_bg)
        corner_lbl.grid(row=8, column=0, sticky=tk.NSEW)
        self.board_canvas = ChessBoardCanvas(board_area_frame, self.on_square_clicked_slot)
        self.board_canvas.grid(row=0, column=1, rowspan=8, columnspan=8, sticky=tk.NSEW)
        self._setup_board_squares()

        control_panel_frame = tk.Frame(main_layout_frame, bg=ChessGameModelTkStyles.COLOR_PANEL_BG, padx=15, pady=15)
        control_panel_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(20,0), expand=False)
        
        self.btn_new_game_white = self._create_button(control_panel_frame, "Новая игра (Белыми)",
                                                      lambda: self.game_controller.new_game(player_is_white_gui_override=True) if self.game_controller else None)
        self.btn_new_game_black = self._create_button(control_panel_frame, "Новая игра (Черными)",
                                                      lambda: self.game_controller.new_game(player_is_white_gui_override=False) if self.game_controller else None)
        
        stretch_frame = tk.Frame(control_panel_frame, bg=ChessGameModelTkStyles.COLOR_PANEL_BG)
        stretch_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        status_bar_container = tk.Frame(self, bg=ChessGameModelTkStyles.COLOR_WINDOW_BG)
        status_bar_container.pack(side=tk.BOTTOM, fill=tk.X)
        status_bar_top_border = tk.Frame(status_bar_container, height=1, bg=ChessGameModelTkStyles.COLOR_WINDOW_BG)
        status_bar_top_border.pack(side=tk.TOP, fill=tk.X)
        self.status_bar_label = tk.Label(status_bar_container, text="Инициализация GUI...",
                                         font=ChessGameModelTkStyles.STATUS_FONT,
                                         bg=ChessGameModelTkStyles.COLOR_PANEL_BG,
                                         fg=ChessGameModelTkStyles.COLOR_TEXT_LIGHT,
                                         anchor=tk.W, padx=5, pady=3)
        self.status_bar_label.pack(side=tk.TOP, fill=tk.X)
        self._update_board_coordinates_labels()

    def _create_button(self, parent, text, command): 
        button = tk.Button(parent, text=text, command=command, width=20)
        normal_style = ChessGameModelTkStyles.get_button_normal_style()
        hover_style = ChessGameModelTkStyles.get_button_hover_style()
        button.config(**normal_style)
        button.bind("<Enter>", lambda e, b=button, s=hover_style: b.config(**s))
        button.bind("<Leave>", lambda e, b=button, s=normal_style: b.config(bg=s["bg"]))
        button.pack(pady=6, fill=tk.X)
        return button

    def _setup_board_squares(self):
        for r_gui in range(8):
            for c_gui in range(8):
                x1, y1 = c_gui * SQUARE_SIZE, r_gui * SQUARE_SIZE
                x2, y2 = x1 + SQUARE_SIZE, y1 + SQUARE_SIZE
                color_idx = (c_gui + r_gui) % 2
                fill_color = ChessGameModelTkStyles.COLOR_BOARD_LIGHT if color_idx == 0 else ChessGameModelTkStyles.COLOR_BOARD_DARK
                self.square_original_colors[r_gui][c_gui] = fill_color
                rect_id = self.board_canvas.create_rectangle(x1, y1, x2, y2, fill=fill_color, outline="")
                self.square_bg_item_ids[r_gui][c_gui] = rect_id

    def _set_square_fill_color(self, r_gui, c_gui, color): 
        item_id = self.square_bg_item_ids[r_gui][c_gui]
        if item_id: self.board_canvas.itemconfig(item_id, fill=color)
    def _reset_square_fill_color(self, r_gui, c_gui): 
        original_color = self.square_original_colors[r_gui][c_gui]
        if original_color: self._set_square_fill_color(r_gui, c_gui, original_color)
    def _set_piece_on_square(self, r_gui, c_gui, symbol, piece_color_is_white): 
        old_piece_id = self.piece_item_ids[r_gui][c_gui]
        if old_piece_id: self.board_canvas.delete(old_piece_id); self.piece_item_ids[r_gui][c_gui] = None
        if not symbol: return
        x_center, y_center = (c_gui + 0.5) * SQUARE_SIZE, (r_gui + 0.5) * SQUARE_SIZE
        text_color = "#FFFFFF" if piece_color_is_white else "#1E1E1E"
        new_piece_id = self.board_canvas.create_text(
            x_center, y_center, text=symbol, font=ChessGameModelTkStyles.PIECE_FONT, fill=text_color,
            tags=f"piece_{r_gui}_{c_gui}")
        self.piece_item_ids[r_gui][c_gui] = new_piece_id

    def _update_board_coordinates_labels(self):
        if not self.game_controller: return
        player_pov_white = self.game_controller.get_player_color_is_white_for_gui()
        files_display = [chr(ord('A') + i) for i in range(8)]
        if not player_pov_white: files_display.reverse()
        for c_gui in range(8):
            if self.file_labels_gui[c_gui]: self.file_labels_gui[c_gui].config(text=files_display[c_gui])
        ranks_display = [str(8 - i) for i in range(8)]
        if not player_pov_white: ranks_display = [str(1 + i) for i in range(8)]
        for r_gui in range(8):
            if self.rank_labels_gui[r_gui]: self.rank_labels_gui[r_gui].config(text=ranks_display[r_gui])

    def update_board_display_slot(self):
        if not self.game_controller or self.is_closing : return
        current_elo_in_title = self.game_controller.current_maia_elo if self.game_controller else DEFAULT_MAIA_ELO
        expected_title = f"Шахматы против Maia ELO {current_elo_in_title}"
        if self.title() != expected_title:
            self.title(expected_title)

        self._update_board_coordinates_labels()
        current_board_obj = self.game_controller.get_current_board_object_for_gui()
        for r_gui in range(8):
            for c_gui in range(8): self._reset_square_fill_color(r_gui, c_gui)

        self.last_move_squares_gui_coords = []
        if self.game_controller.get_board_logic_for_gui().board.move_stack: 
            last_move = self.game_controller.get_board_logic_for_gui().board.peek()
            from_sq_board, to_sq_board = last_move.from_square, last_move.to_square
            self.last_move_squares_gui_coords = [
                self._board_to_gui_coords(chess.square_rank(from_sq_board), chess.square_file(from_sq_board)),
                self._board_to_gui_coords(chess.square_rank(to_sq_board), chess.square_file(to_sq_board))
            ]
        for r_gui in range(8):
            for c_gui in range(8):
                file_idx, rank_idx = self._gui_to_board_coords(r_gui, c_gui)
                square_chess_index = chess.square(file_idx, rank_idx)
                piece = current_board_obj.piece_at(square_chess_index)
                piece_symbol_char, is_white_piece_on_square = ("", False)
                if piece:
                    piece_symbol_char = self.piece_symbols[piece.symbol()]
                    is_white_piece_on_square = piece.color == chess.WHITE
                self._set_piece_on_square(r_gui, c_gui, piece_symbol_char, is_white_piece_on_square)
        for r_lm, c_lm in self.last_move_squares_gui_coords:
            if 0 <= r_lm < 8 and 0 <= c_lm < 8: self._set_square_fill_color(r_lm, c_lm, ChessGameModelTkStyles.COLOR_HIGHLIGHT_LAST_MOVE)
        if self.selected_square_gui_coords:
            r_sel, c_sel = self.selected_square_gui_coords
            self._set_square_fill_color(r_sel, c_sel, ChessGameModelTkStyles.COLOR_HIGHLIGHT_SELECTED)
        for r_pm, c_pm in self.possible_moves_for_selected_gui_coords:
            self._set_square_fill_color(r_pm, c_pm, ChessGameModelTkStyles.COLOR_HIGHLIGHT_POSSIBLE)
        self.board_canvas.update_idletasks()

    def show_game_over_message_slot(self, message):
        if self.is_closing: return
        self.update_status_bar_slot(message) 
        messagebox.showinfo("Игра окончена", message, parent=self)

    def update_status_bar_slot(self, message):
        if self.is_closing: return
        if hasattr(self, 'status_bar_label'): 
             self.status_bar_label.config(text=message)
        else:
            print(f"DEBUG (chess_board GUI): status_bar_label not found, message: {message}")

    def _gui_to_board_coords(self, r_gui, c_gui): 
        player_pov_white = self.game_controller.get_player_color_is_white_for_gui()
        file_idx = c_gui if player_pov_white else 7 - c_gui
        rank_idx = 7 - r_gui if player_pov_white else r_gui
        return file_idx, rank_idx
    def _board_to_gui_coords(self, rank_idx, file_idx): 
        player_pov_white = self.game_controller.get_player_color_is_white_for_gui()
        c_gui = file_idx if player_pov_white else 7 - file_idx
        r_gui = 7 - rank_idx if player_pov_white else rank_idx
        return r_gui, c_gui

    def on_square_clicked_slot(self, r_gui, c_gui):
        if not self.game_controller or self.is_closing: return
        current_board_obj = self.game_controller.get_current_board_object_for_gui()
        if current_board_obj.is_game_over() or self.game_controller.engine_is_thinking: return

        file_idx, rank_idx = self._gui_to_board_coords(r_gui, c_gui)
        clicked_square_chess_index = chess.square(file_idx, rank_idx)

        if self.selected_square_gui_coords is None:
            piece = current_board_obj.piece_at(clicked_square_chess_index)
            board_turn_color = self.game_controller.get_board_logic_for_gui().get_turn()
            
            is_player_gui_turn = (self.game_controller.player_is_white_in_gui and board_turn_color == chess.WHITE) or \
                                 (not self.game_controller.player_is_white_in_gui and board_turn_color == chess.BLACK)

            if piece and piece.color == board_turn_color and is_player_gui_turn:
                self.selected_square_gui_coords = (r_gui, c_gui)
                self.possible_moves_for_selected_gui_coords = []
                for move in current_board_obj.legal_moves:
                    if move.from_square == clicked_square_chess_index:
                        to_r_gui, to_c_gui = self._board_to_gui_coords(
                            chess.square_rank(move.to_square), chess.square_file(move.to_square))
                        self.possible_moves_for_selected_gui_coords.append((to_r_gui, to_c_gui))
            elif not is_player_gui_turn:
                 self.update_status_bar_slot("Сейчас не ваш ход (ожидается ход Maia/LLM).")
            else:
                current_turn_color_str = "белых" if board_turn_color == chess.WHITE else "черных"
                self.update_status_bar_slot(f"Выберите фигуру {current_turn_color_str} / Пустой квадрат.")
        else:
            from_r_gui, from_c_gui = self.selected_square_gui_coords
            from_file_idx, from_rank_idx = self._gui_to_board_coords(from_r_gui, from_c_gui)
            from_square_chess_index = chess.square(from_file_idx, from_rank_idx)
            uci_move_str = chess.Move(from_square_chess_index, clicked_square_chess_index).uci()
            piece_at_from = current_board_obj.piece_at(from_square_chess_index)
            if piece_at_from and piece_at_from.piece_type == chess.PAWN:
                target_rank_for_promo_board = 7 if current_board_obj.turn == chess.WHITE else 0
                if rank_idx == target_rank_for_promo_board:
                    is_legal_promo_move = any(m for m in current_board_obj.legal_moves
                                             if m.from_square == from_square_chess_index and
                                                m.to_square == clicked_square_chess_index and m.promotion)
                    if is_legal_promo_move:
                        items = {"Ферзь": "q", "Ладья": "r", "Слон": "b", "Конь": "n"}
                        dialog = PromotionDialog(self, "Превращение пешки", items)
                        promo_piece_char = dialog.result_value
                        if promo_piece_char: uci_move_str += promo_piece_char
                        else:
                            self.update_status_bar_slot("Превращение отменено. Ход не сделан.")
                            self.selected_square_gui_coords = None
                            self.possible_moves_for_selected_gui_coords = []
                            self.update_board_display_slot() 
                            return
            self.game_controller.handle_player_move_from_gui(uci_move_str)
            self.selected_square_gui_coords = None
            self.possible_moves_for_selected_gui_coords = []
        self.update_board_display_slot()

    def on_closing_event(self): 
        if messagebox.askyesno("Выход", "Вы уверены, что хотите выйти из шахмат?", parent=self):
            self.is_closing = True 
            print("CONSOLE (chess_board GUI): Окно GUI закрывается пользователем.")

def run_chess_gui_process(command_q: multiprocessing.Queue, state_q: multiprocessing.Queue,
                          initial_elo: int, player_is_white_gui: bool):
    print(f"CONSOLE (chess_board_process): >>> ЗАПУСК ПРОЦЕССА GUI. ELO: {initial_elo}, Игрок GUI белый: {player_is_white_gui}")
    
    app_instance_ref = {"instance": None} 
    logged_command_q_none_warning_for_this_run = False

    # Create a queue for GUI events from other threads
    gui_event_queue = queue.Queue()

    def _proxy_update_status(message):
        if app_instance_ref["instance"] and not app_instance_ref["instance"].is_closing and message is not None:
            gui_event_queue.put(("status_update", message))
        # Removed direct app.after call
        return None 
        
    def _proxy_update_board():
        if app_instance_ref["instance"] and not app_instance_ref["instance"].is_closing:
            gui_event_queue.put(("board_update", None))
        # Removed direct app.after call
                
    def _proxy_game_over(message):
        if app_instance_ref["instance"] and not app_instance_ref["instance"].is_closing:
            gui_event_queue.put(("game_over", message))
        # Removed direct app.after call

    game_controller = None
    app = None 
    try:
        print(f"CONSOLE (chess_board_process): [STAGE 1] Создание ChessGameController...")
        game_controller = ChessGameController(
            initial_elo=initial_elo,
            player_is_white_gui=player_is_white_gui,
            state_q=state_q,
            status_update_cb_gui=_proxy_update_status, # Proxies now use gui_event_queue
            board_update_cb_gui=_proxy_update_board,   # Proxies now use gui_event_queue
            game_over_cb_gui=_proxy_game_over          # Proxies now use gui_event_queue
        )
        print(f"CONSOLE (chess_board_process): [STAGE 1] ChessGameController создан.")

        print(f"CONSOLE (chess_board_process): [STAGE 2] Вызов game_controller.initialize_dependencies_and_engine()...")
        if not game_controller.initialize_dependencies_and_engine():
            print(f"CONSOLE (chess_board_process): [STAGE 2] ОШИБКА: initialize_dependencies_and_engine() ВЕРНУЛ FALSE. Процесс GUI завершается.")
            return 

        print(f"CONSOLE (chess_board_process): [STAGE 2] initialize_dependencies_and_engine() УСПЕШНО ВЫПОЛНЕН.")
        
        print(f"CONSOLE (chess_board_process): [STAGE 3] Создание ChessGuiTkinter (окна)...")
        app = ChessGuiTkinter(game_controller)
        app_instance_ref["instance"] = app
        print(f"CONSOLE (chess_board_process): [STAGE 3] ChessGuiTkinter (окно) СОЗДАНО.")

        print(f"CONSOLE (chess_board_process): [STAGE 4] Вызов game_controller.new_game()...")
        game_controller.new_game() 
        print(f"CONSOLE (chess_board_process): [STAGE 4] game_controller.new_game() ВЫПОЛНЕН.")

        print(f"CONSOLE (chess_board_process): [STAGE 5] >>> ВХОД В ГЛАВНЫЙ ЦИКЛ ОБНОВЛЕНИЯ GUI...")
        while not app.is_closing:
            # Process commands from the main application (if command_q is provided)
            try:
                if command_q: 
                    command = command_q.get_nowait()
                    if command:
                        print(f"CONSOLE (chess_board_process): [LOOP] Получена команда: {command}")
                        if command.get("action") == "stop_gui_process": 
                            print(f"CONSOLE (chess_board_process): [LOOP] Команда stop_gui_process, выход из цикла.")
                            app.is_closing = True
                            break
                        if command.get("action") == "resign" or command.get("action") == "stop": 
                             print(f"CONSOLE (chess_board_process): [LOOP] Команда resign/stop, обработка и выход.")
                             if game_controller: game_controller.process_command(command) 
                             app.is_closing = True 
                             break
                        if game_controller: game_controller.process_command(command)
                else: 
                    if not logged_command_q_none_warning_for_this_run:
                        print("CONSOLE (chess_board_process): [LOOP] WARNING: command_q is None. External command processing via queue will be skipped.")
                        logged_command_q_none_warning_for_this_run = True
                    pass 
            except queue.Empty:
                pass 
            except Exception as e_loop_command:
                print(f"CONSOLE (chess_board_process): [LOOP] Ошибка в цикле обработки команд: {e_loop_command}")
                traceback.print_exc() 

            # Process GUI events from the gui_event_queue
            try:
                while not gui_event_queue.empty():
                    event_type, data = gui_event_queue.get_nowait()
                    if app_instance_ref["instance"] and not app_instance_ref["instance"].is_closing:
                        current_app_gui = app_instance_ref["instance"]
                        if event_type == "status_update":
                            if hasattr(current_app_gui, 'update_status_bar_slot'):
                                current_app_gui.update_status_bar_slot(data)
                        elif event_type == "board_update":
                            if hasattr(current_app_gui, 'update_board_display_slot'):
                                current_app_gui.update_board_display_slot()
                        elif event_type == "game_over":
                            if hasattr(current_app_gui, 'show_game_over_message_slot'):
                                current_app_gui.show_game_over_message_slot(data)
            except queue.Empty:
                pass # No GUI events to process
            except Exception as e_gui_event_loop:
                print(f"CONSOLE (chess_board_process): [LOOP] Ошибка в цикле обработки GUI событий: {e_gui_event_loop}")
                traceback.print_exc()


            # Ensure app exists and is updated
            if app: 
                app.update_idletasks()
                app.update()
            else: 
                print("CONSOLE (chess_board_process): [LOOP] CRITICAL: 'app' is None in main loop. Breaking.")
                break
            time.sleep(0.05) 
        
        print(f"CONSOLE (chess_board_process): [STAGE 5] <<< ВЫХОД ИЗ ГЛАВНОГО ЦИКЛА GUI.")

    except Exception as e_main_run_try:
        print(f"CONSOLE (chess_board_process): КРИТИЧЕСКАЯ ОШИБКА В ОСНОВНОМ TRY-EXCEPT ПРОЦЕССА GUI: {e_main_run_try}")
        traceback.print_exc() 
        if state_q: 
            try:
                state_q.put({"error": f"Critical unhandled error in GUI process: {str(e_main_run_try)}", "critical_process_failure": True})
            except Exception as e_queue_put:
                print(f"CONSOLE (chess_board_process): Не удалось отправить критическую ошибку (основной try) в state_q: {e_queue_put}")
    finally:
        print(f"CONSOLE (chess_board_process): [FINALLY] Блок finally процесса GUI.")
        if game_controller:
            print(f"CONSOLE (chess_board_process): [FINALLY] Вызов game_controller.shutdown_engine_process().")
            game_controller.shutdown_engine_process()
        
        if app and app_instance_ref.get("instance"): 
            print(f"CONSOLE (chess_board_process): [FINALLY] Попытка app.destroy(). is_closing={app.is_closing if hasattr(app, 'is_closing') else 'N/A'}")
            try:
                 app.destroy()
                 print(f"CONSOLE (chess_board_process): [FINALLY] app.destroy() вызван.")
            except tk.TclError as e_destroy_tcl_app:
                 print(f"CONSOLE (chess_board_process): [FINALLY] Ошибка TclError при app.destroy(): {e_destroy_tcl_app} (возможно, окно уже было уничтожено или не создано)")
            except Exception as e_destroy_generic_app:
                print(f"CONSOLE (chess_board_process): [FINALLY] Непредвиденная ошибка при app.destroy(): {e_destroy_generic_app}")
                traceback.print_exc()
        elif app_instance_ref.get("instance"): 
            print(f"CONSOLE (chess_board_process): [FINALLY] app не был присвоен в try, но app_instance_ref['instance'] существует. Попытка destroy() для instance.")
            try:
                 app_instance_ref["instance"].destroy()
            except Exception as e_destroy_instance_alt:
                 print(f"CONSOLE (chess_board_process): [FINALLY] Ошибка при app_instance_ref['instance'].destroy(): {e_destroy_instance_alt}")
                 traceback.print_exc()

        print(f"CONSOLE (chess_board_process): >>> ПРОЦЕСС GUI ЗАВЕРШЕН.")

if __name__ == '__main__':
    print("Локальный тест chess_board.py (запуск GUI процесса)")
    cmd_q = multiprocessing.Queue()
    st_q = multiprocessing.Queue()
    gui_process = multiprocessing.Process(target=run_chess_gui_process, args=(cmd_q, st_q, 1500, True), daemon=True)
    gui_process.start()
    def monitor_queues():
        while True:
            try:
                state = st_q.get(timeout=1)
                print(f"[MAIN TEST] Получено состояние из GUI процесса: {state.get('fen', 'N/A FEN')}, Turn: {state.get('turn')}, Outcome: {state.get('outcome_message')}, Error: {state.get('error')}")
                if state.get("is_game_over") or state.get("error") or state.get("game_resigned_by_llm") or state.get("game_stopped_by_llm") or state.get("critical_process_failure"):
                    print("[MAIN TEST] Игра окончена, ошибка или критический сбой процесса GUI, завершение мониторинга.")
                    if gui_process.is_alive():
                         cmd_q.put({"action":"stop_gui_process"}) 
                    break
            except queue.Empty: pass
            except Exception as e_monitor: 
                print(f"[MAIN TEST] Ошибка чтения из state_queue: {e_monitor}")
                traceback.print_exc()
                break
            time.sleep(0.1)
        print("[MAIN TEST] Мониторинг завершен.")
    monitor_thread = threading.Thread(target=monitor_queues, daemon=True) 
    monitor_thread.start()
    time.sleep(15) 
    if gui_process.is_alive(): print("[MAIN TEST] Отправка команды на ход движка..."); cmd_q.put({"action": "engine_move"})
    time.sleep(10)
    if gui_process.is_alive(): print("[MAIN TEST] Отправка команды на смену ELO..."); cmd_q.put({"action": "change_elo", "elo": 1100})
    gui_process.join(timeout=60) 
    if gui_process.is_alive(): print("[MAIN TEST] GUI процесс не завершился, терминируем."); gui_process.terminate()
    print("[MAIN TEST] Тест завершен.")