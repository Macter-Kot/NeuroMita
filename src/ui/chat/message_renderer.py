import io
import base64
import time
from PyQt6.QtGui import QTextCursor, QColor, QImage, QFont, QPalette
from utils import _
from main_logger import logger
from ui.chat.chat_delegate import ChatMessageDelegate

def _get_delegate(gui) -> ChatMessageDelegate:
    if hasattr(gui, "chat_delegate") and gui.chat_delegate:
        return gui.chat_delegate
    d = ChatMessageDelegate()
    setattr(gui, "chat_delegate", d)
    return d

def insert_message(gui, role, content, insert_at_start=False, message_time=""):
    if not hasattr(gui, '_images_in_chat'):
        gui._images_in_chat = []

    processed_content_parts = []
    has_image_content = False

    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    processed_content_parts.append({"type": "text", "content": item.get("text", ""), "tag": "default"})
                elif item.get("type") == "image_url":
                    has_image_content = process_image_for_chat(gui, has_image_content, item, processed_content_parts)
        if has_image_content and not any(part["type"] == "text" and part["content"].strip() for part in processed_content_parts):
            processed_content_parts.insert(0, {"type": "text", "content": _("<Изображение экрана>", "<Screen Image>") + "\n", "tag": "default"})
    elif isinstance(content, str):
        processed_content_parts.append({"type": "text", "content": content, "tag": "default"})
    else:
        return

    delegate = _get_delegate(gui)
    hide_tags = gui._get_setting("HIDE_CHAT_TAGS", False)

    # Разбиваем текст на части делегатом
    normalized_parts = []
    for part in processed_content_parts:
        if part["type"] == "text":
            normalized_parts.extend(delegate.split_text_with_tags(part["content"], hide_tags))
        else:
            normalized_parts.append(part)

    cursor = gui.chat_window.textCursor()
    show_timestamps = gui._get_setting("SHOW_CHAT_TIMESTAMPS", False)
    timestamp_str = delegate.get_timestamp(show_timestamps, message_time)

    if insert_at_start:
        cursor.movePosition(QTextCursor.MoveOperation.Start)
    else:
        cursor.movePosition(QTextCursor.MoveOperation.End)

    if show_timestamps and timestamp_str:
        _insert_formatted_text(gui, cursor, timestamp_str, QColor("#888888"), italic=True)

    # Лейбл спикера (включая system)
    label_text, label_color, label_bold = delegate.get_label(gui, role)
    _insert_formatted_text(gui, cursor, label_text, label_color, bold=label_bold)

    # Контент (системным — отдельный цвет)
    content_color = delegate.get_content_color(role)

    for part in normalized_parts:
        if part["type"] == "text":
            color = None
            if part.get("tag") == "tag_green":
                color = delegate.tag_color
            else:
                color = content_color  # для system — окрашиваем контент
            _insert_formatted_text(gui, cursor, part["content"], color)
        elif part["type"] == "image":
            cursor.insertImage(part["content"])
            cursor.insertText("\n")

    insert_message_end(gui, cursor, role)

    if not insert_at_start:
        gui.chat_window.verticalScrollBar().setValue(gui.chat_window.verticalScrollBar().maximum())

def insert_message_end(gui, cursor=None, role="assistant"):
    if not cursor:
        cursor = gui.chat_window.textCursor()
    if role == "user":
        cursor.insertText("\n")
    elif role in {"assistant", "system"}:
        cursor.insertText("\n\n")

def insert_speaker_name(gui, cursor=None, role="assistant"):
    delegate = _get_delegate(gui)
    if not cursor:
        cursor = gui.chat_window.textCursor()
    label_text, label_color, label_bold = delegate.get_label(gui, role)
    _insert_formatted_text(gui, cursor, label_text, label_color, bold=label_bold)

def _insert_formatted_text(gui, cursor, text, color=None, bold=False, italic=False):
    char_format = cursor.charFormat()
    if color:
        char_format.setForeground(color)
    else:
        default_text_color = gui.chat_window.palette().color(QPalette.ColorRole.Text)
        char_format.setForeground(default_text_color)
    font = QFont("Arial", int(gui._get_setting("CHAT_FONT_SIZE", 12)))
    font.setBold(bold)
    font.setItalic(italic)
    char_format.setFont(font)
    cursor.insertText(text, char_format)

def append_message(gui, text):
    cursor = gui.chat_window.textCursor()
    cursor.movePosition(QTextCursor.MoveOperation.End)
    _insert_formatted_text(gui, cursor, text)
    gui.chat_window.verticalScrollBar().setValue(gui.chat_window.verticalScrollBar().maximum())

def prepare_stream_slot(gui):
    insert_speaker_name(gui, role="assistant")

def append_stream_chunk_slot(gui, chunk):
    append_message(gui, chunk)

def finish_stream_slot(gui):
    insert_message_end(gui, role="assistant")

def process_image_for_chat(gui, has_image_content, item, processed_content_parts):
    image_data_base64 = item.get("image_url", {}).get("url", "")
    if image_data_base64.startswith("data:image/jpeg;base64,"):
        image_data_base64 = image_data_base64.replace("data:image/jpeg;base64,", "")
    elif image_data_base64.startswith("data:image/png;base64,"):
        image_data_base64 = image_data_base64.replace("data:image/png;base64,", "")
    try:
        from PIL import Image
        image_bytes = base64.b64decode(image_data_base64)
        image = Image.open(io.BytesIO(image_bytes))
        max_width = 400
        max_height = 300
        original_width, original_height = image.size
        if original_width > max_width or original_height > max_height:
            ratio = min(max_width / original_width, max_height / original_height)
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        image_bytes = io.BytesIO()
        image.save(image_bytes, format='PNG')
        image_bytes.seek(0)
        qimage = QImage()
        qimage.loadFromData(image_bytes.getvalue())
        processed_content_parts.append({"type": "image", "content": qimage})
        has_image_content = True
    except Exception as e:
        logger.error(f"Ошибка при декодировании или обработке изображения: {e}")
        processed_content_parts.append({"type": "text", "content": _("<Ошибка загрузки изображения>", "<Image load error>")})
    return has_image_content