from typing import Optional
from rent.base_processor import BaseRentProcessor
from FunPayAPI.types import OrderShortcut, UserProfile
from FunPayAPI.account import Account
from rent.game_type import GameType
import time
from logging_config import get_logger
from FunPayAPI.common.enums import SubCategoryTypes

logger = get_logger(__name__)



class CommonRentProcessor(BaseRentProcessor):
    def __init__(self, account: Account, profile: UserProfile, processors_dict=None, gt_keys_dict=None):
        super().__init__(account)
        self.game_type = GameType.NONE
        self.profile = profile
        self._processors_dict = processors_dict  # Ссылка на словарь процессоров из FunPayManager
        self._gt_keys_dict = gt_keys_dict  # Ссылка на словарь game_type -> ключ процессора

    def change_lots_status(self):
        pass

    def auto_reply(self, message):
        pass

    def create_missing_lots(self):
        pass

    def get_code(self, login: str):
        pass

    def kick(self, login: str, password: str):
        """
        CommonRentProcessor не может выкинуть пользователя напрямую,
        так как не знает тип игры. Метод должен вызываться через правильный процессор.
        """
        logger.warning(f"⚠️ kick вызван для CommonRentProcessor (не должен вызываться напрямую для логина {login})")
    
    def _get_processor_by_game_type(self, game_type: GameType):
        """
        Получает правильный процессор по game_type.
        """
        if self._gt_keys_dict and self._processors_dict:
            processor_key = self._gt_keys_dict.get(game_type)
            if processor_key:
                return self._processors_dict.get(processor_key)
        return None


    def on_sale(self, order: OrderShortcut):
        pass

    def on_sale_extend(self, order: OrderShortcut, original_order_id):
        pass

    def auto_raise_lots(self):
        """
        Функция автоподнятия лотов.
        Работает в отдельном потоке и поднимает лоты каждые 2 часа.
        """
        if not self.profile or not self.profile.get_lots():
            logger.info("[AUTO-RAISE] Нет лотов для поднятия")
            return
        
        logger.info("[AUTO-RAISE] 🚀 Автоподнятие лотов запущено!")
        raise_times = {}  # Время следующего поднятия для каждой категории
        RAISE_INTERVAL = 2 * 60 * 60
        while True:
            try:
                
                # Собираем уникальные категории из лотов
                unique_categories = []
                seen_category_ids = set()
                
                for subcat_obj in self.profile.get_sorted_lots(2).keys():
                    if subcat_obj.category.id not in seen_category_ids:
                        unique_categories.append(subcat_obj.category)
                        seen_category_ids.add(subcat_obj.category.id)
                
                sorted_categories = sorted(unique_categories, key=lambda cat: cat.position)
                next_raise_time = float("inf")
                
                # Поднимаем лоты для каждой категории
                for category in sorted_categories:
                    # Проверяем, не рано ли поднимать эту категорию
                    saved_time = raise_times.get(category.id)
                    if saved_time and saved_time > int(time.time()):
                        next_raise_time = min(next_raise_time, saved_time)
                        continue
                    
                    # Собираем активные подкатегории для этой категории
                    active_subcats = []
                    for subcat, lots in self.profile.get_sorted_lots(2).items():
                        if (subcat.category.id == category.id and 
                            subcat.type == SubCategoryTypes.COMMON and lots):
                            active_subcats.append(subcat)
                    
                    unique_subcats = list(set(sc.id for sc in active_subcats))
                    
                    if not unique_subcats:
                        raise_times[category.id] = int(time.time()) + RAISE_INTERVAL
                        next_raise_time = min(next_raise_time, raise_times[category.id])
                        continue
                    
                    # Поднимаем лоты!
                    try:
                        time.sleep(1.5)  # Небольшая задержка
                        self.account.raise_lots(category.id, subcategories=unique_subcats)
                        logger.info(f"[AUTO-RAISE] ✅ Лоты подняты для категории: {category.name}")
                        
                        # Запоминаем время следующего поднятия
                        next_time = int(time.time()) + RAISE_INTERVAL
                        raise_times[category.id] = next_time
                        next_raise_time = min(next_raise_time, next_time)
                        
                    except Exception as e:
                        logger.debug(f"[AUTO-RAISE] Ошибка при поднятии '{category.name}': {e}")
                        # При ошибке пробуем снова через 60 секунд
                        raise_times[category.id] = int(time.time()) + 60
                        next_raise_time = min(next_raise_time, raise_times[category.id])
                
                # Спим до следующего поднятия
                delay = next_raise_time - int(time.time()) if next_raise_time < float("inf") else 300
                if delay > 0:
                    logger.debug(f"[AUTO-RAISE] Следующее поднятие через {delay // 60} минут {delay % 60} секунд")
                    time.sleep(delay)
                else:
                    time.sleep(3)
                    
            except Exception as e:
                logger.error(f"[AUTO-RAISE] Критическая ошибка в цикле поднятия: {e}")
                time.sleep(60)


    def run_tasks(self):
        self.start_task(self.find_expired_rents)
        self.start_task(self.auto_raise_lots)
        