import httpx
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

async def get_part_analogs(part_number: str) -> str:
    """Ищет аналоги запчасти по артикулу и возвращает красивый текст."""
    api_key = os.getenv("RAPIDAPI_KEY")
    if not api_key:
        logger.error("RAPIDAPI_KEY не найден в .env")
        return "Ошибка: сервис поиска запчастей временно недоступен."

    url = "https://auto-parts-cross-reference-api.p.rapidapi.com/v1/crosses"
    
    headers = {
        "x-rapidapi-host": "auto-parts-cross-reference-api.p.rapidapi.com",
        "x-rapidapi-key": api_key
    }
    
    clean_number = part_number.replace(" ", "")
    
    params = {
        "number": clean_number,
        "lang": "en"
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                return "Не удалось получить данные от API запчастей."

            data = response.json()
            results = data.get("r", [])
            
            if not results:
                return f"По артикулу {part_number} ничего не найдено."

            result_text = f"Результаты поиска по артикулу {part_number}:\n"
            
            for item in results:
                part_info = item.get("p", {})
                brand = part_info.get("b", "Неизвестно")
                number = part_info.get("n", "")
                description = part_info.get("d", "")
                
                result_text += f"\nДеталь: {brand} {number} ({description})\n"
                
                analogs = item.get("a", [])
                if analogs:
                    result_text += "Аналоги:\n"
                    for analog in analogs[:5]:
                        a_info = analog.get("p", {})
                        a_brand = a_info.get("b", "")
                        a_number = a_info.get("n", "")
                        result_text += f" - {a_brand} {a_number}\n"
                    
                    if len(analogs) > 5:
                        result_text += f" ... и еще {len(analogs) - 5} аналогов.\n"

            return result_text

        except Exception as e:
            logger.error(f"Ошибка запроса к API запчастей: {e}")
            return "Произошла ошибка при поиске запчастей."