"""
CLI: установка и проверка Telegram webhook (токен и URL из ENV).

Запуск из корня проекта:

    python -m core.cli.webhook_cli info
    python -m core.cli.webhook_cli set
    python -m core.cli.webhook_cli delete
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Корень проекта в sys.path, если запускают как файл
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.webhook_management import (
    delete_webhook,
    get_webhook_info,
    set_webhook_from_settings,
    webhook_info_to_dict,
)
from bot.webhook_url import resolve_telegram_webhook_url
from core.config.settings import get_settings
from core.integrations.telegram_client import create_telegram_bot


async def cmd_info() -> None:
    settings = get_settings()
    bot = create_telegram_bot(settings)
    try:
        info = await get_webhook_info(bot)
        print(json.dumps(webhook_info_to_dict(info), indent=2, ensure_ascii=False))
    finally:
        await bot.session.close()


async def cmd_set() -> None:
    settings = get_settings()
    url = resolve_telegram_webhook_url(settings)
    print("Webhook URL:", url)
    bot = create_telegram_bot(settings)
    try:
        ok = await set_webhook_from_settings(bot, settings)
        print("setWebhook ok:", ok)
        info = await get_webhook_info(bot)
        print("Текущее состояние:")
        print(json.dumps(webhook_info_to_dict(info), indent=2, ensure_ascii=False))
    finally:
        await bot.session.close()


async def cmd_delete(drop_pending: bool) -> None:
    settings = get_settings()
    bot = create_telegram_bot(settings)
    try:
        ok = await delete_webhook(bot, drop_pending_updates=drop_pending)
        print("deleteWebhook ok:", ok)
    finally:
        await bot.session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Telegram webhook: info / set / delete")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="Показать getWebhookInfo (JSON)")

    sub.add_parser("set", help="Вызвать setWebhook по URL из env")

    p_del = sub.add_parser("delete", help="Снять webhook")
    p_del.add_argument(
        "--drop-pending",
        action="store_true",
        help="Очистить необработанные обновления (drop_pending_updates)",
    )

    args = parser.parse_args()

    if args.command == "info":
        asyncio.run(cmd_info())
    elif args.command == "set":
        asyncio.run(cmd_set())
    elif args.command == "delete":
        asyncio.run(cmd_delete(args.drop_pending))
    else:
        parser.print_help()
        raise SystemExit(1)


if __name__ == "__main__":
    main()
