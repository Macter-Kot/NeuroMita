import zipapp
import pathlib

# --- Это и есть ваш "файл с правилами", только в виде функции ---
def my_awesome_filter(path: pathlib.Path) -> bool:
    """
    Эта функция решает, включать ли файл/папку в архив.
    Она возвращает True, если файл НУЖНО добавить, и False, если его НУЖНО проигнорировать.
    """
        
    # 2. Игнорируем папку с тестами целиком
    # 'tests' in path.parts проверяет, есть ли папка 'tests' в пути
    if 'include' in path.parts or 'Prompts' in path.parts or 'PromptsCatalogue' in path.parts or 'ReadmeFiles' in path.parts or 'MitaAiC#' in path.parts or '__pycache__' in path.parts:
        print(f"Игнорирую тестовый файл/папку: {path}")
        return False

    # 3. Игнорируем все файлы, которые заканчиваются на .log или .tmp
    if path.suffix in ['.log', '.tmp', '.test']:
        print(f"Игнорирую временный файл: {path}")
        return False
        
    # 4. Игнорируем конкретные файлы по имени
    if path.name == 'notes_for_dev.txt':
        print(f"Игнорирую файл с заметками: {path}")
        return False

    # Если ни одно из правил не сработало, включаем файл в архив
    print(f"Добавляю: {path}")
    return True

# --- Основная логика сборки ---
if __name__ == "__main__":
    print("Начинаю сборку zip-приложения...")
    name = 'NeuroMita.pyz'
    zipapp.create_archive(
        source='src',                    # Папка с исходниками
        target=name,           # Имя выходного архива
        filter=my_awesome_filter,        # !!! Вот здесь мы применяем наш фильтр !!!
        compressed=True                  # Сжимаем архив для уменьшения размера
    )
    
    print(f"\nСборка {name} успешно завершена!")