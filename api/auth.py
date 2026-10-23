"""Проверка подлинности данных, которые Telegram передаёт в Mini App.

Telegram подписывает initData секретным ключом, производным от BOT_TOKEN.
Если подпись не сходится — данные подделаны.
"""

import hashlib
import hmac
from urllib.parse import parse_qsl


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверяет подпись initData. Возвращает словарь или None при ошибке."""
    if not init_data:
        return None

    # Разбираем строку вида "query_id=...&user=...&auth_date=...&hash=..."
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", None)
    if not received_hash:
        return None

    # Формируем строку для проверки: все пары ключ=значение, отсортированные
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    # Секретный ключ: HMAC-SHA256("WebAppData", BOT_TOKEN)
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()

    # Считаем подпись и сравниваем
    calculated = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(calculated, received_hash):
        return None

    return parsed
