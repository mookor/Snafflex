import requests

# Матрица MMR по [звёзды-1][ранг-1]
# Ранги: 1=Herald, 2=Guardian, 3=Crusader, 4=Archon, 5=Legend, 6=Ancient, 7=Divine
RANK_MATRIX = [
    [1,   770,  1540, 2310, 3080, 3850, 4620],  # 1 звезда
    [154, 924,  1694, 2464, 3234, 4004, 4820],  # 2 звезды
    [308, 1078, 1848, 2618, 3388, 4158, 5020],  # 3 звезды
    [462, 1232, 2002, 2772, 3542, 4312, 5220],  # 4 звезды
    [616, 1386, 2156, 2926, 3696, 4466, 5420],  # 5 звёзд
]


def get_rank(account_id: str | int) -> int | None:
    """
    Получает примерный MMR игрока по Dota ID через OpenDota API.
    
    :param account_id: Dota 2 Account ID (не Steam ID!)
    :return: MMR или None если не удалось получить
    """
    url = f"https://api.opendota.com/api/players/{account_id}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        rank_tier = data.get('rank_tier')
        if not rank_tier:
            return None  
        
        rank_str = str(rank_tier)
        rank = int(rank_str[0])   # Ранг (1-7)
        stars = int(rank_str[1])  # Звёзды (1-5)
        
        if 1 <= rank <= 7 and 1 <= stars <= 5:
            return RANK_MATRIX[stars - 1][rank - 1]
        
        return None
        
    except (requests.RequestException, KeyError, ValueError, IndexError):
        return None 