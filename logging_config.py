import logging
import os
from logging.handlers import RotatingFileHandler

# Папка для логов
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "funpay.log")

# Создаём папку для логов, если её нет
os.makedirs(LOG_DIR, exist_ok=True)


def setup_logging(level: int = logging.INFO):
    """
    Настраивает логирование для всего приложения.
    Логи пишутся в консоль и в файл logs/funpay.log
    
    :param level: Уровень логирования (по умолчанию INFO)
    """
    # Формат логов
    log_format = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    formatter = logging.Formatter(log_format, datefmt=date_format)
    
    # Получаем корневой логгер
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Очищаем существующие обработчики
    root_logger.handlers.clear()
    
    # Обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Обработчик для файла (ротация: макс 10MB, хранить 5 файлов)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Уменьшаем логи от сторонних библиотек
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    logging.info(f"📝 Логирование настроено. Файл: {LOG_FILE}")


def get_logger(name: str) -> logging.Logger:
    """
    Возвращает логгер с указанным именем.
    Автоматически настраивает логирование, если оно еще не настроено.
    
    :param name: Имя логгера (обычно __name__)
    :return: Объект Logger
    """
    root_logger = logging.getLogger()
    # Автоматически настраиваем логирование, если обработчиков еще нет
    if not root_logger.handlers:
        setup_logging()
    
    return logging.getLogger(name)

