
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
from logging_config import get_logger

logger = get_logger(__name__)
class FunPayManager:
    def __init__(self):
        self.processors: dict[str, BaseRentProcessor] = {}
        self.rent_keys: list[str] = []
        self.gt_keys: dict[GameType, str] = {}
        self.db = RentDatabase()
        self._init_funpay()

    @property
    def _common_processor(self) -> CommonRentProcessor:
        return self.processors["CommonRentProcessor"]  # type: ignore
        

    def add_processor(self, key, processor: BaseRentProcessor, is_rent = False, game_type = None):

        self.processors[key] = processor(self.account)
        if is_rent:
            self.rent_keys.append(key)
            self.gt_keys[game_type] = key
        
        # Обновляем ссылки на процессоры в CommonRentProcessor после добавления нового процессора
        if "CommonRentProcessor" in self.processors:
            common_proc = self.processors["CommonRentProcessor"]
            if hasattr(common_proc, '_processors_dict'):
                common_proc._processors_dict = self.processors
                common_proc._gt_keys_dict = self.gt_keys


    def _init_funpay(self):
        try:
            self.account = Account(FunPayConfig.TOKEN, FunPayConfig.USER_AGENT).get()
            self.account_id = self.account.id
            self.profile = self.account.get_user(self.account_id)
            self.runner = Runner(
                self.account,
                disable_message_requests=False,
                disabled_order_requests=False,
                disabled_buyer_viewing_requests=True,
            )
            self.processors["CommonRentProcessor"] = CommonRentProcessor(
            self.account, self.profile, 
            processors_dict=self.processors, 
            gt_keys_dict=self.gt_keys
        )
            logger.info(f"✅ FunPay подключен: {self.account.username}")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при инициализации FunPay: {e}", exc_info=True)
            raise

    def _run_tasks(self):
        for k, processor in self.processors.items():
            try:
                processor.run_tasks()
            except Exception as e:
                logger.error(f"❌ Ошибка при запуске задач процессора {k}: {e}", exc_info=True)

    def run(self):
        self._run_tasks()
        self._main_loop()

    def _main_loop(self):
        while True:
            try:
                for event in self.runner.listen(4):
                    try:
                        if event.type is enums.EventTypes.NEW_ORDER:
                            self._handle_new_order(event)
                        if event.type is enums.EventTypes.NEW_MESSAGE:
                            if event.message.type is MessageTypes.NEW_FEEDBACK:
                                self._handle_feedback(event)
                            else:
                                self._handle_new_message(event)
                    except Exception as e:
                        logger.error(f"❌ Ошибка при обработке события {event.type}: {e}", exc_info=True)
                        # Продолжаем работу, не падаем на одной ошибке
                        continue
            except KeyboardInterrupt:
                logger.info("🛑 Получен сигнал остановки")
                raise
            except Exception as e:
                logger.error(f"❌ Критическая ошибка в главном цикле: {e}", exc_info=True)
                time.sleep(5)  # Небольшая задержка перед повтором
    
    def _handle_feedback(self, event):
        try:
            processor: CommonRentProcessor = self._common_processor
            ORDER_ID_PATTERN = re.compile(r"#([A-Z0-9]{8})")
            match = ORDER_ID_PATTERN.search(event.message.text)
            if not match:
                return
            order_id = match.group(1)
            logger.info(f"⭐ Отзыв: заказ {order_id}")
            chat_id = getattr(event.message, 'chat_id', None)
            processor.on_review(order_id, chat_id=chat_id)
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке отзыва: {e}", exc_info=True)

    def _handle_rent_order(self, order):
        try:
            processor: BaseRentProcessor = self.processors[order.subcategory_name]

            EXTEND_LOT_PATTERN = re.compile(r"Продление заказа:?\s*([A-Z0-9]+)", re.IGNORECASE)
            extend_match = EXTEND_LOT_PATTERN.search(order.description)
            if extend_match:
                original_order_id = extend_match.group(1)
                processor.on_sale_extend(order, original_order_id)
            else:
                processor.on_sale(order)
        except KeyError as e:
            logger.error(f"❌ Процессор для подкатегории {order.subcategory_name} не найден: {e}")
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке заказа {order.id}: {e}", exc_info=True)

    def _handle_new_order(self, event):
        """
        Вызывается, когда приходит новый оплаченный заказ
        """
        try:
            order = event.order
            if order.subcategory_name in self.rent_keys:
                self._handle_rent_order(order)
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке нового заказа: {e}", exc_info=True)
        
    def _handle_new_message(self, event: EventTypes):
        try:
            message = event.message
            if message.author == FunPayConfig.ADMIN_NAME:
                return

            buyer_id = message.author_id
            
            chat_id = message.chat_id
            message_text = message.text
            if not message_text:
                return
            message_text = message_text.strip().lower()
            if message_text.startswith("!"):
                self._handle_command(message_text, buyer_id, chat_id)
        except Exception as e:
            logger.error(f"❌ Ошибка при обработке сообщения: {e}", exc_info=True)


    def _parse_order_id(self, message: str, cmd: str, chat_id: str) -> str | None:
        """Извлекает order_id из команды. Возвращает None и шлёт ошибку если формат неверный."""
        try:
            parts = message.split()
            if len(parts) < 2:
                self.account.send_message(
                    chat_id,
                    f"❌ Неверный формат команды.\n"
                    f"Используйте: {cmd} <номер_заказа>\n"
                    f"Например: {cmd} ABC12345"
                )
                return None
            return parts[1].upper()
        except Exception as e:
            logger.error(f"❌ Ошибка при парсинге order_id из команды: {e}", exc_info=True)
            try:
                self.account.send_message(chat_id, "❌ Произошла ошибка при обработке команды.")
            except:
                pass
            return None

    def _get_rent_or_error(self, order_id: str, chat_id: str):
        """Возвращает аренду или None с отправкой ошибки."""
        try:
            rent = self.db.get_rental_by_order_id(order_id)
            if not rent:
                try:
                    self.account.send_message(chat_id, "❌ Заказ не найден.")
                except:
                    logger.error(f"❌ Не удалось отправить сообщение об ошибке в чат {chat_id}")
            return rent
        except Exception as e:
            logger.error(f"❌ Ошибка при получении аренды {order_id}: {e}", exc_info=True)
            try:
                self.account.send_message(chat_id, "❌ Произошла ошибка при обработке запроса.")
            except:
                pass
            return None

    def _handle_command(self, message: str, buyer_id: int, chat_id: str):
        try:
            if message == "!время":
                self._common_processor.on_get_time(buyer_id, chat_id=chat_id)
                return

            if message.startswith("!продлить"):
                if order_id := self._parse_order_id(message, "!продлить", chat_id):
                    logger.info(f"📝 Команда !продлить: {order_id}")
                    self._common_processor.on_extend(order_id, buyer_id, chat_id=chat_id)
                return

            if message.startswith("!code"):
                if not (order_id := self._parse_order_id(message, "!code", chat_id)):
                    return
                if rent := self._get_rent_or_error(order_id, chat_id):
                    logger.info(f"🔐 Команда !code: {order_id}")
                    processor = self.processors.get(self.gt_keys.get(rent.game_type))
                    if processor:
                        processor.on_get_code(order_id, buyer_id, chat_id=chat_id)
                    else:
                        logger.error(f"❌ Процессор для {rent.game_type} не найден")
                        try:
                            self.account.send_message(chat_id, "❌ Произошла ошибка при обработке команды.")
                        except:
                            pass
                return

            if message.startswith("!ban"):
                if not (order_id := self._parse_order_id(message, "!ban", chat_id)):
                    return
                if not (rent := self._get_rent_or_error(order_id, chat_id)):
                    return
                try:
                    if rent.buyer_id != buyer_id:
                        self.account.send_message(chat_id, "❌ Этот заказ не принадлежит вам.")
                        return
                    if (time.time() - rent.start_rent_time) > 60 * 10:
                        self.account.send_message(
                            chat_id,
                            "К сожалению, время для автоматического возврата средств истекло.\n"
                            "Пожалуйста, дождитесь ответа администратора."
                        )
                        logger.warning(f"⚠️ Команда !ban просрочена: {order_id}")
                        return
                    logger.info(f"🚫 Команда !ban: {order_id}")
                    reply_message = (
                        "😔 Приносим извинения за неудобства!\n\n"
                        "Средства были автоматически возвращены.\n"
                        "Спасибо за понимание! Надеемся, вы вернётесь к нам снова. 🙏"
                    )
                    processor = self.processors.get(self.gt_keys.get(rent.game_type))
                    if processor:
                        processor.on_return(
                            order_id, buyer_id, reply_message, rent.account_login, chat_id=chat_id
                        )
                    else:
                        logger.error(f"❌ Процессор для {rent.game_type} не найден")
                except Exception as e:
                    logger.error(f"❌ Ошибка при обработке команды !ban: {e}", exc_info=True)
                return

            if message.startswith("!free") or message.startswith("!acc"):
                self.account.send_message(chat_id, "🎮 Все открытые лоты в профиле — это разные аккаунты для аренды.\n✅ Если лот виден (открыт) — значит аккаунт свободен и вы можете его арендовать прямо сейчас!")
                return
            self.account.send_message(chat_id, "❌ Неизвестная команда")
        except Exception as e:
            logger.error(f"❌ Критическая ошибка при обработке команды: {e}", exc_info=True)
            try:
                self.account.send_message(chat_id, "❌ Произошла ошибка при обработке команды. Попробуйте позже.")
            except:
                pass
