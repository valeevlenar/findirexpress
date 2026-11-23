"""Настройка профиля ИП и двух получателей через существующие записи FindirExpress."""

import argparse
import asyncio
import os
import re

import asyncpg


async def provision_profile(conn, *, issuer_inn, issuer_name, owner_tg_id, seller_ids):
    if re.fullmatch(r"[0-9]{12}", issuer_inn) is None:
        raise ValueError("Для ИП нужен 12-значный ИНН")
    if len(seller_ids) != 2 or len(set(seller_ids)) != 2:
        raise ValueError("Укажите два разных seller_id получателей")

    async with conn.transaction():
        user_id = await conn.fetchval("SELECT id FROM users WHERE tg_id = $1", owner_tg_id)
        if user_id is None:
            raise ValueError("Пользователь Telegram должен уже существовать в FindirExpress")

        sellers = await conn.fetch(
            "SELECT id, seller_inn, seller_title FROM sellers "
            "WHERE id = ANY($1::int[]) ORDER BY id FOR SHARE",
            seller_ids,
        )
        if len(sellers) != 2:
            raise ValueError("Оба кабинета WB должны существовать")
        if any(re.fullmatch(r"[0-9]{10}", seller["seller_inn"]) is None for seller in sellers):
            raise ValueError("У обоих получателей должен быть 10-значный ИНН")

        issuer_id = await _participant(conn, issuer_inn, issuer_name, "ip", None)
        await conn.execute(
            "INSERT INTO marking_access (participant_id, user_id, role) VALUES ($1, $2, 'admin') "
            "ON CONFLICT (participant_id, user_id) DO UPDATE SET role = EXCLUDED.role",
            issuer_id, user_id,
        )
        recipient_ids = {}
        for seller in sellers:
            recipient_id = await _participant(
                conn, seller["seller_inn"], seller["seller_title"], "company", seller["id"],
            )
            await conn.execute(
                "INSERT INTO marking_routes (issuer_id, recipient_id) VALUES ($1, $2) "
                "ON CONFLICT DO NOTHING",
                issuer_id, recipient_id,
            )
            recipient_ids[seller["id"]] = recipient_id
        return issuer_id, recipient_ids


async def _participant(conn, inn, name, kind, seller_id):
    participant_id = await conn.fetchval(
        "INSERT INTO marking_participants (inn, name, kind, seller_id) VALUES ($1, $2, $3, $4) "
        "ON CONFLICT (inn) DO UPDATE SET name = EXCLUDED.name "
        "WHERE marking_participants.kind = EXCLUDED.kind "
        "AND marking_participants.seller_id IS NOT DISTINCT FROM EXCLUDED.seller_id "
        "RETURNING id",
        inn, name, kind, seller_id,
    )
    if participant_id is None:
        raise ValueError("Участник с таким ИНН уже связан с другим профилем")
    return participant_id


async def _main(args, dsn):
    conn = await asyncpg.connect(dsn)
    try:
        issuer_id, recipients = await provision_profile(
            conn, issuer_inn=args.issuer_inn, issuer_name=args.issuer_name,
            owner_tg_id=args.owner_tg_id, seller_ids=args.recipient_seller_ids,
        )
        print(f"Профиль ИП: {issuer_id}. Получатели (seller_id → participant_id): {recipients}")
    finally:
        await conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issuer-inn", required=True)
    parser.add_argument("--issuer-name", required=True)
    parser.add_argument("--owner-tg-id", required=True, type=int)
    parser.add_argument("--recipient-seller-ids", nargs=2, required=True, type=int)
    args = parser.parse_args()
    dsn = os.getenv("FINDIREXPRESS_MARKING_TEST_DSN")
    if not dsn:
        parser.error("Укажите DSN тестовой базы в FINDIREXPRESS_MARKING_TEST_DSN")
    asyncio.run(_main(args, dsn))
