from typing import Optional
from rent.base_processor import BaseRentProcessor
from FunPayAPI.types import OrderShortcut
from FunPayAPI.account import Account
from rent.game_type import GameType

from logging_config import get_logger

logger = get_logger(__name__)



class CommonRentProcessor(BaseRentProcessor):
    def __init__(self, account: Account):
        super().__init__(account)
        self.game_type = GameType.NONE
        logger.info(f"✅ Инициализирован CommonRentProcessor для аккаунта {account.username}")

    def change_lots_status(self):
        pass

    def auto_reply(self, message):
        pass

    def create_missing_lots(self):
        pass

    def get_code(self, login: str):
        pass

    def kick(self, login: str, password: str):
        pass


    def on_sale(self, order: OrderShortcut):
        pass

    def on_sale_extend(self, order: OrderShortcut, original_order_id):
        pass
