import zipapp
import pathlib

def bin_filter(path: pathlib.Path) -> bool:
    if 'include' in path.parts or 'Prompts' in path.parts or 'PromptsCatalogue' in path.parts or 'ReadmeFiles' in path.parts or 'MitaAiC#' in path.parts or '__pycache__' in path.parts:
        print(f"Игнорирую тестовый файл/папку: {path}")
        return False

    if path.suffix in ['.log', '.tmp', '.test']:
        print(f"Игнорирую временный файл: {path}")
        return False
        
    print(f"Добавляю: {path}")
    return True

if __name__ == "__main__":
    print("Начинаю сборку zip-приложения...")
    name = 'NeuroMita.pyz'
    zipapp.create_archive(
        source='src',
        target=name,
        filter=bin_filter,
        compressed=True
    )
    
    print(f"\nСборка {name} успешно завершена!")