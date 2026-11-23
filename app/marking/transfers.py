"""Изменения резерва, владельца и истории выполняются одной транзакцией."""


async def reserve_code(conn, *, transfer_id, code_id):
    async with conn.transaction():
        transfer = await conn.fetchrow(
            "SELECT environment, sender_id, status, created_by FROM marking_transfers WHERE id = $1 FOR UPDATE",
            transfer_id,
        )
        if not transfer or transfer["status"] != "draft":
            raise ValueError("Коды можно добавлять только в черновик передачи")
        code = await conn.fetchrow(
            "SELECT owner_id, environment FROM marking_codes WHERE id = $1 FOR UPDATE", code_id,
        )
        if not code or code["owner_id"] != transfer["sender_id"] or code["environment"] != transfer["environment"]:
            raise ValueError("Код должен принадлежать отправителю и тому же контуру")
        added = await conn.fetchval(
            "INSERT INTO marking_transfer_codes (transfer_id, code_id, environment) VALUES ($1, $2, $3) "
            "ON CONFLICT (transfer_id, code_id) DO NOTHING RETURNING code_id",
            transfer_id, code_id, transfer["environment"],
        )
        if added is not None:
            await conn.execute(
                "INSERT INTO marking_events (code_id, environment, transfer_id, event_type, source, "
                "source_event_id, actor_user_id, occurred_at) "
                "VALUES ($1, $2, $3, 'transfer_reserved', 'findirexpress', $3::bigint::text, $4, now())",
                code_id, transfer["environment"], transfer_id, transfer["created_by"],
            )


async def confirm_transfer(conn, *, transfer_id, gismt_document_id, confirmed_at):
    """Вызывать после проверки, что ГИС МТ приняла УПД по всем кодам передачи."""
    if not gismt_document_id or not gismt_document_id.strip() or confirmed_at.utcoffset() is None:
        raise ValueError("Нужны ID документа ГИС МТ и время подтверждения с часовым поясом")

    async with conn.transaction():
        transfer = await conn.fetchrow(
            "SELECT sender_id, recipient_id, status, gismt_document_id FROM marking_transfers WHERE id = $1 FOR UPDATE",
            transfer_id,
        )
        if transfer and transfer["status"] == "confirmed" and transfer["gismt_document_id"] == gismt_document_id:
            return
        if not transfer or transfer["status"] != "signed":
            raise ValueError("Подтвердить можно только подписанную передачу")
        if transfer["gismt_document_id"] not in (None, gismt_document_id):
            raise ValueError("Документ ГИС МТ не совпадает с записанным")

        reserved = await conn.fetchval(
            "SELECT count(*) FROM marking_transfer_codes WHERE transfer_id = $1 AND released_at IS NULL", transfer_id,
        )
        updated = await conn.fetch(
            "UPDATE marking_codes AS c SET owner_id = $2 FROM marking_transfer_codes AS tc "
            "WHERE tc.transfer_id = $1 AND tc.code_id = c.id AND tc.released_at IS NULL AND c.owner_id = $3 "
            "RETURNING c.id",
            transfer_id, transfer["recipient_id"], transfer["sender_id"],
        )
        if not reserved or len(updated) != reserved:
            raise ValueError("В передаче нет кодов либо часть уже не принадлежит отправителю")
        await conn.execute(
            "INSERT INTO marking_events (code_id, environment, transfer_id, event_type, source, "
            "source_event_id, occurred_at) "
            "SELECT code_id, environment, transfer_id, 'transfer_confirmed', 'gismt', $2, $3 "
            "FROM marking_transfer_codes WHERE transfer_id = $1 AND released_at IS NULL",
            transfer_id, gismt_document_id, confirmed_at,
        )
        await conn.execute(
            "UPDATE marking_transfer_codes SET released_at = now() WHERE transfer_id = $1 AND released_at IS NULL",
            transfer_id,
        )
        await conn.execute(
            "UPDATE marking_transfers SET status = 'confirmed', confirmed_at = $2, gismt_document_id = $3 WHERE id = $1",
            transfer_id, confirmed_at, gismt_document_id,
        )
