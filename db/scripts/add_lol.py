from db.database import RentDatabase
from db.rent_tables import LolAccountInfo
from rent.game_type import GameType


def add_lol_account(
    login: str,
    password: str,
    rank: str,
    profile_link: str,
    db_path: str = "rent.db"
) -> bool:
    """
    Добавить LoL аккаунт в базу данных.
    
    Args:
        login: Логин аккаунта
        password: Пароль
        rank: Ранг (например "Diamond 1")
        profile_link: Ссылка на профиль
        db_path: Путь к базе данных
    
    Returns:
        True если успешно добавлен
    """
    db = RentDatabase(db_path)
    
    account = LolAccountInfo(
        login=login,
        password=password,
        rented_by=None,
        game_type=GameType.LOL,
        rank=rank,
        profile_link=profile_link
    )
    
    return db.add_account(account)


if __name__ == "__main__":
    # Пример использования
    add_lol_account(
        login="example_login",
        password="example_pass",
        rank="Diamond 1",
        profile_link="https://op.gg/summoners/euw/example"
    )
    print("LoL аккаунт добавлен!")

