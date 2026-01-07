from db.database import RentDatabase
from db.rent_tables import DotaAccountInfo
from rent.game_type import GameType


def add_dota_account(
    login: str,
    password: str,
    behavior_score: int,
    dota_id: int,
    mmr: int,
    profile_link: str,
    db_path: str = "rent.db"
) -> bool:
    """
    Добавить Dota аккаунт в базу данных.
    
    Args:
        login: Логин аккаунта
        password: Пароль
        behavior_score: Поведение (0-10000)
        dota_id: Dota ID
        mmr: MMR рейтинг
        profile_link: Ссылка на профиль
        db_path: Путь к базе данных
    
    Returns:
        True если успешно добавлен
    """
    db = RentDatabase(db_path)
    
    account = DotaAccountInfo(
        login=login,
        password=password,
        rented_by=None,
        game_type=GameType.DOTA,
        behavior_score=behavior_score,
        dota_id=dota_id,
        mmr=mmr,
        profile_link=profile_link
    )
    
    return db.add_account(account)


if __name__ == "__main__":
    # Пример использования
    add_dota_account(
        login="example_login",
        password="example_pass",
        behavior_score=10000,
        dota_id=123456789,
        mmr=5000,
        profile_link="https://dotabuff.com/players/123456789"
    )
    print("Dota аккаунт добавлен!")

