
from FunPayAPI import Account, Runner, types, enums
from FunPayAPI.common.enums import EventTypes
from FunPayManager.config import FunPayConfig
from rent.game_type import GameType
from rent.base_processor import BaseRentProcessor
from rent.common.processor import CommonRentProcessor
from db.database import RentDatabase
import re
from FunPayAPI.common.enums import MessageTypes
import time
class FunPayManager:
    def __init__(self, ):
        self.processors = {}
        self._init_funpay()
        self.rent_keys = []
        self.gt_keys = {}
        self.db = RentDatabase()
        

    def add_processor(self, key, processor: BaseRentProcessor, is_rent = False, game_type = None):

        self.processors[key] = processor(self.account)
        if is_rent:
            self.rent_keys.append(key)
            self.gt_keys[game_type] = key


    def _init_funpay(self):
        self.account = Account(FunPayConfig.TOKEN, FunPayConfig.USER_AGENT).get()
        self.account_id = self.account.id
        self.profile = self.account.get_user(self.account_id)
        self.runner = Runner(
            self.account,
            disable_message_requests=False,
            disabled_order_requests=False,
            disabled_buyer_viewing_requests=True,
        )
        self.processors["CommonRentProcessor"] = CommonRentProcessor(self.account)

    def _run_tasks(self):
        for k, processor in self.processors.items():
            processor.run_tasks()

    def run(self):
        self._run_tasks()
        self._main_loop()

    def _main_loop(self):
        for event in self.runner.listen(4):
            if event.type is enums.EventTypes.NEW_ORDER:
                self._handle_new_order(event)
            if event.type is enums.EventTypes.NEW_MESSAGE:
                if event.message.type is MessageTypes.NEW_FEEDBACK:
                    self._handle_feedback(event)
                else:
                    self._handle_new_message(event)
    
    def _handle_feedback(self, event):
        processor: CommonRentProcessor = self.processors["CommonRentProcessor"]
        ORDER_ID_PATTERN = re.compile(r"#([A-Z0-9]{8})")
        match = ORDER_ID_PATTERN.search(event.message.text)
        if not match:
            return
        order_id = match.group(1)
        processor.on_review(order_id)

    def _handle_rent_order(self, order):
        processor: BaseRentProcessor = self.processors[order.subcategory_name]

        EXTEND_LOT_PATTERN = re.compile(r"Продление заказа:?\s*([A-Z0-9]+)", re.IGNORECASE)
        extend_match = EXTEND_LOT_PATTERN.search(order.description)
        if extend_match:
            original_order_id = extend_match.group(1)
            processor.on_sale_extend(order, original_order_id)
        else:
            processor.on_sale(order)

    def _handle_new_order(self, event):
        """
        Вызывается, когда приходит новый оплаченный заказ
        """
        order = event.order
        if order.subcategory_name  in self.rent_keys:
            self._handle_rent_order(order)
        
    def _handle_new_message(self, event: EventTypes):
        

        message = event.message
        if message.author == FunPayConfig.ADMIN_NAME:
            return

        buyer_id = message.author_id
        
        chat_id = message.chat_id
        message_text = message.text
        message_text = message_text.strip().lower()
        if message_text.startswith("!"):
            self._handle_command(message_text, buyer_id, chat_id)


    def _handle_command(self, message: str, buyer_id: int, chat_id: str):
        if message.startswith("!продлить"):
            parts = message.split()
            if len(parts) < 2:
                self.account.send_message(
                    chat_id,
                    "❌ Неверный формат команды.\n"
                    "Используйте: !продлить <номер_заказа>\n"
                    "Например: !продлить ABC12345"
                )
            order_id = parts[1].upper()
            processor: CommonRentProcessor = self.processors["CommonRentProcessor"]
            processor.on_extend(order_id, buyer_id)
        elif message == "!время":
            processor: CommonRentProcessor = self.processors["CommonRentProcessor"]
            processor.on_get_time(buyer_id)

        elif message.startswith("!code"):
            parts = message.split()
            if len(parts) < 2:
                self.account.send_message(
                    chat_id,
                    "❌ Неверный формат команды.\n"
                    "Используйте: !code <номер_заказа>\n"
                    "Например: !code ABC12345"
                )
                return

            order_id = parts[1].upper()
            rent = self.db.get_rental_by_order_id(order_id)
            if not rent:
                self.account.send_message(chat_id, "❌ Заказ не найден.\nПравильное использование: !code <id заказа>\nНапример: !code ABC12345")
                return
            processor: BaseRentProcessor = self.processors[self.gt_keys[rent.game_type]]
            processor.on_get_code(order_id, buyer_id)
        elif message.startswith("!ban"):
            parts = message.split()
            if len(parts) < 2:
                self.account.send_message(
                    chat_id,
                    "❌ Неверный формат команды.\n"
                    "Используйте: !ban <номер_заказа>\n"
                    "Например: !ban ABC12345"
                )
                return

            order_id = parts[1].upper()
            rent = self.db.get_rental_by_order_id(order_id)
            if not rent:
                self.account.send_message(chat_id, "❌ Заказ не найден.\nПравильное использование: !ban <id заказа>\nНапример: !ban ABC12345")
                return
            if rent.buyer_id != buyer_id:
                self.account.send_message(
                chat_id,
                "❌ Этот заказ не принадлежит вам."
                )
                return
            current_time = time.time()
            cant_auto_return = (current_time - rent.start_rent_time) > 60*10
            if cant_auto_return:
                self.account.send_message(chat_id, f"К сожалению, время для автоматического возврата средств истекло\nПожалуйста, дождитесть ответа администратора")
                return

            processor: BaseRentProcessor = self.processors[self.gt_keys[rent.game_type]]
            reply_message = "😔 Приносим извинения за неудобства!\n\n"
            "Средства были автоматически возвращены.\n"
            "Спасибо за понимание! Надеемся, вы вернётесь к нам снова. 🙏"
            processor.on_return(order_id, buyer_id,reply_message,rent.account_login)
            
        else:
            self.account.send_message(
                    chat_id, "❌ Неизвестная команда")
            
            