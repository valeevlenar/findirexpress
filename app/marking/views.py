from sqlalchemy import text

from app.database.asyncontext import db_session

PAGE_SIZE = 8


async def get_profile(tg_id, issuer_id=None):
    async with db_session() as session:
        profile = (await session.execute(text("""
            SELECT p.id, p.inn, p.name, a.role
            FROM marking_participants p
            JOIN marking_access a ON a.participant_id = p.id
            JOIN users u ON u.id = a.user_id
            WHERE u.tg_id = :tg_id AND p.kind = 'ip'
              AND (CAST(:issuer_id AS bigint) IS NULL OR p.id = :issuer_id)
            ORDER BY p.id LIMIT 1
        """), {"tg_id": tg_id, "issuer_id": issuer_id})).mappings().first()
        if profile is None:
            return None, []

        recipients = (await session.execute(text("""
            SELECT p.name, p.inn, p.seller_id
            FROM marking_routes r
            JOIN marking_participants p ON p.id = r.recipient_id
            WHERE r.issuer_id = :issuer_id
            ORDER BY p.name, p.id
        """), {"issuer_id": profile["id"]})).mappings().all()
        return profile, recipients


async def list_codes(tg_id, issuer_id, page):
    async with db_session() as session:
        return (await session.execute(text("""
            SELECT c.id, c.gtin, right(c.serial, 6) AS serial_tail, c.environment,
                   c.received_at, owner.name AS owner_name
            FROM marking_codes c
            JOIN marking_order_items i ON i.id = c.order_item_id
            JOIN marking_orders o ON o.id = i.order_id
            JOIN marking_access a ON a.participant_id = o.issuer_id
            JOIN users u ON u.id = a.user_id
            JOIN marking_participants owner ON owner.id = c.owner_id
            WHERE o.issuer_id = :issuer_id AND u.tg_id = :tg_id
            ORDER BY c.id DESC LIMIT :limit OFFSET :offset
        """), {"tg_id": tg_id, "issuer_id": issuer_id, "limit": PAGE_SIZE + 1,
                 "offset": page * PAGE_SIZE})).mappings().all()


async def get_code_history(tg_id, issuer_id, code_id, page):
    async with db_session() as session:
        params = {"tg_id": tg_id, "issuer_id": issuer_id, "code_id": code_id}
        code = (await session.execute(text("""
            SELECT c.gtin, right(c.serial, 6) AS serial_tail, c.environment, c.issued_at,
                   c.received_at, owner.name AS owner_name
            FROM marking_codes c
            JOIN marking_order_items i ON i.id = c.order_item_id
            JOIN marking_orders o ON o.id = i.order_id
            JOIN marking_access a ON a.participant_id = o.issuer_id
            JOIN users u ON u.id = a.user_id
            JOIN marking_participants owner ON owner.id = c.owner_id
            WHERE o.issuer_id = :issuer_id AND u.tg_id = :tg_id AND c.id = :code_id
        """), params)).mappings().first()
        if code is None:
            return None, []

        events = (await session.execute(text("""
            SELECT e.event_type, e.source, e.occurred_at, e.recorded_at,
                   actor.username AS actor_name, recipient.name AS recipient_name,
                   t.edo_document_id, t.gismt_document_id
            FROM marking_events e
            LEFT JOIN users actor ON actor.id = e.actor_user_id
            LEFT JOIN marking_transfers t ON t.id = e.transfer_id
            LEFT JOIN marking_participants recipient ON recipient.id = t.recipient_id
            WHERE e.code_id = :code_id
            ORDER BY COALESCE(e.occurred_at, e.recorded_at) DESC, e.id DESC
            LIMIT :limit OFFSET :offset
        """), {"code_id": code_id, "limit": PAGE_SIZE + 1, "offset": page * PAGE_SIZE})).mappings().all()
        return code, events
