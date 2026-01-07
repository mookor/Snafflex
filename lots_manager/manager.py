
from FunPayAPI import Account, types
from FunPayAPI.account import logger
from rent import game_type
from rent.game_type import GameType
from rent.dota.config import DotaConfig
from typing import Optional

class LotsManager:
    configs = {GameType.DOTA: DotaConfig.NODE_ID}

    @staticmethod
    def find_all_game_lots(account: Account, game_type: GameType,) -> list[types.MyLotShortcut]:
        node_id = LotsManager.configs[game_type]
        subcategory_lots = account.get_my_subcategory_lots(node_id)
        lots = []
        for lot in subcategory_lots:
            lots.append(lot)
        return lots


    @staticmethod
    def find_lot_by_login(account: Account, game_type: GameType, login: str) -> Optional[types.MyLotShortcut]:
        try:
            node_id = LotsManager.configs[game_type]
            subcategory_lots = account.get_my_subcategory_lots(node_id)
            for lot in subcategory_lots:
                if login in lot.description:
                    return lot
            return None
        except:
            pass

    @staticmethod
    def find_extend_lot(account: Account, order_id:str, game_type: GameType):
        node_id = LotsManager.configs[game_type]
        subcategory_lots = account.get_my_subcategory_lots(node_id)
        for lot in subcategory_lots:
            if order_id in lot.description:
                return lot
        return None

    @staticmethod
    def create_dota_rent(account: Account, mmr: int, login: str, active: bool, behavior_score: int):
        title_ru = DotaConfig.LOT_TITLE_TEMPLATE_RU.format(mmr=mmr, login=login)
        title_en = DotaConfig.LOT_TITLE_TEMPLATE_EN.format(mmr=mmr, login=login)
        fields = {
            "csrf_token": account.csrf_token,
            "offer_id": "0",
            "node_id": str(DotaConfig.NODE_ID),
            "fields[summary][ru]": title_ru,
            "fields[summary][en]": title_en,
            "fields[desc][ru]": DotaConfig.LOT_DESCRIPTION_RU,
            "fields[desc][en]": DotaConfig.LOT_DESCRIPTION_EN,
            "fields[payment_msg][ru]": "",
            "fields[payment_msg][en]": "",
            "price": str(DotaConfig.PRICE),
            "deactivate_after_sale": "on",
            "active": "on" if active else "",
            "amount": "100",
            "secrets": "",
            "auto_delivery": "",
            "fields[solommr]" : str(mmr),
            "fields[decency]": str(behavior_score),
            "fields[type1]": "Аренда"
        }
        lot_fields = types.LotFields(0, fields)
        account.save_lot(lot_fields)
        
    @staticmethod
    def create_extend_lot(account: Account, order_id: str, price: int):
        title_ru = f"Продление заказа {order_id}"
        title_en = f"Extend order {order_id}"
        fields = {
            "csrf_token": account.csrf_token,
            "offer_id": "0",
            "node_id": str(DotaConfig.NODE_ID),
            "fields[summary][ru]": title_ru,
            "fields[summary][en]": title_en,
            "fields[desc][ru]": f"Продление заказа {order_id}\n1шт = 1 час",
            "fields[desc][en]": f"Extend: {order_id}\n1p = 1 hour",
            "fields[payment_msg][ru]": "",
            "fields[payment_msg][en]": "",
            "price": str(price),
            "deactivate_after_sale": "on",
            "active": "on",
            "amount": "100",
            "secrets": "",
            "auto_delivery": "",
            "fields[solommr]" : str(1),
            "fields[decency]": str(1),
            "fields[type1]": "Аренда"
        }
        lot_fields = types.LotFields(0, fields)
        account.save_lot(lot_fields)

    @staticmethod
    def recreate_lot(account: Account, game_type: GameType, login:str):
        lot = LotsManager.find_lot_by_login(account, game_type, login)
        if lot:
            
            lot_fields = account.get_lot_fields(lot.id)
            account.delete_lot(lot.id)

            lot_fields.lot_id = 0
            lot_fields.active = True
            lot_fields.amount = 100
            lot_fields.fields["offer_id"] = "0"
            account.save_lot(lot_fields)
            return True
        else:
            return False


    @staticmethod
    def create_rent_lot(game_type, *args, **kwargs):
        
        if game_type == GameType.DOTA:
            LotsManager.create_dota_rent(*args, **kwargs)

    @staticmethod
    def disable_lot(account: Account, lot:types.MyLotShortcut):
        lot_fields = account.get_lot_fields(lot.id)
        lot_fields.active = False
        account.save_lot(lot_fields)

    @staticmethod
    def enable_lot(account: Account, lot:types.MyLotShortcut):
        lot_fields = account.get_lot_fields(lot.id)
        lot_fields.active = True
        account.save_lot(lot_fields)

    @staticmethod
    def update_mmr(account: Account, lot: types.MyLotShortcut, new_mmr: int, login: str):
        """Обновить MMR в лоте для Dota аккаунта."""
        lot_fields = account.get_lot_fields(lot.id)
        
        # Обновляем MMR
        lot_fields.fields["fields[solommr]"] = str(new_mmr)
        lot_fields.title_ru = DotaConfig.LOT_TITLE_TEMPLATE_RU.format(mmr=new_mmr, login=login)
        lot_fields.title_en = DotaConfig.LOT_TITLE_TEMPLATE_EN.format(mmr=new_mmr, login=login)
        account.save_lot(lot_fields)
        
if __name__ == "__main__":
    FUNPAY_TOKEN = "8nhu2drjgvf99h9509j7kftojpnd9w8c"
    FUNPAY_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    FUNPAY_ADMIN_NAME = "Mookor"



    account = Account(FUNPAY_TOKEN, FUNPAY_USER_AGENT).get()
    # LotsManager.create_rent_lot(GameType.DOTA, account, 11000,'ZXC', False, 123)
    print(LotsManager.find_lot_by_login(account, GameType.DOTA, "jrjnnhsx2094").id)
    _, orders, _, _ = account.get_sales(
                include_paid=True,
                include_closed=False,
                include_refunded=False,
                state="paid"
            )
    zxc = 1 