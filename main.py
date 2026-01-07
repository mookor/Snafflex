
from logging_config import setup_logging
from FunPayManager.manager import FunPayManager
from rent.game_type import GameType
from rent.dota.processor import DotaRentProcessor
from rent.dota.config import DotaConfig

if __name__ == "__main__":
    # Настройка логирования (должно быть первым)
    setup_logging()
    
    fp_manager = FunPayManager()
    fp_manager.add_processor(key = DotaConfig.SUBCATEGORY_NAME, processor = DotaRentProcessor, is_rent=True, game_type = GameType.DOTA)
    
    fp_manager.run()