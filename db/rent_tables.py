from dataclasses import dataclass
from rent.game_type import GameType
from typing import Optional
from enum import Enum

class PayedStatus(Enum):
    BUYED = 1
    PAYED = 2
    REFUND = 3

@dataclass
class RentalInfo:
    buyer_id : int
    start_rent_time: float
    end_rent_time: float
    order_id: str
    game_type: GameType
    account_login: str
    income: float
    amount: int
    notifed: bool = False
    feedback_bonus_given: bool = False
    in_rent: bool = True
    payed: PayedStatus = PayedStatus.BUYED
    
    


@dataclass
class AccountInfo:
    login: str
    password: str
    rented_by: Optional[int]
    game_type: GameType
    is_busy: bool = False
    is_banned: bool = False

@dataclass(kw_only=True)
class DotaAccountInfo(AccountInfo):
    behavior_score: int
    dota_id: int
    mmr: int
    profile_link: str

@dataclass(kw_only=True)
class ValorantAccountInfo(AccountInfo):
    rank: str
    profile_link: str

    
@dataclass(kw_only=True)
class LolAccountInfo(AccountInfo):
    rank: str
    profile_link: str

