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
    # Устанавливаем минимальный уровень на DEBUG, чтобы пропускать все логи
    # Затем фильтруем на уровне обработчиков
    root_logger.setLevel(logging.DEBUG)
    
    # Очищаем существующие обработчики
    root_logger.handlers.clear()
    
    # Обработчик для консоли - устанавливаем уровень явно
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)  # INFO будет показывать INFO, WARNING, ERROR, CRITICAL
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Обработчик для файла (ротация: макс 10MB, хранить 5 файлов)
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setLevel(level)  # INFO будет показывать INFO, WARNING, ERROR, CRITICAL
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
    
    # Уменьшаем логи от сторонних библиотек
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Явно устанавливаем уровень для наших модулей, чтобы гарантировать логирование
    # Это гарантирует, что даже если логгер создан до setup_logging, он будет работать
    logging.getLogger("auth.steam.steam_client").setLevel(logging.INFO)
    logging.getLogger("rent").setLevel(logging.INFO)
    logging.getLogger("rent.base_processor").setLevel(logging.INFO)
    logging.getLogger("rent.dota.processor").setLevel(logging.INFO)
    logging.getLogger("FunPayManager").setLevel(logging.INFO)
    
    # Убеждаемся, что propagation включен (по умолчанию True, но на всякий случай)
    for logger_name in ["auth.steam.steam_client", "rent", "rent.base_processor", 
                        "rent.dota.processor", "FunPayManager"]:
        logger = logging.getLogger(logger_name)
        logger.propagate = True
    
    logging.info(f"📝 Логирование настроено. Файл: {LOG_FILE}, Уровень: {logging.getLevelName(level)}")


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

