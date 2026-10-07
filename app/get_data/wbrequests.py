from app.database.apirequests import ApiClient
from app.wrappers import with_session

# GET /api/v5/supplier/reportDetailByPeriod отключен WB (release-notes id=498, ~28.09.2026).
# Замена - детализация отчетов реализации за период из финансового API: та же пагинация
# по rrdId, но POST, поля в camelCase и денежные суммы строками. Нужен токен с категорией "Финансы".
sales_url = 'https://finance-api.wildberries.ru/api/finance/v1/sales-reports/detailed'

SALES_PAGE_LIMIT = 100000

# Ключ старого v5 -> ключ нового API. Остальной код (sales_report_compilation,
# check_three_barcodes, пагинация по rrd_id) по-прежнему работает со старыми ключами.
_SALES_FIELD_MAP = {
    'realizationreport_id': 'reportId',
    'date_from': 'dateFrom',
    'date_to': 'dateTo',
    'create_dt': 'createDate',
    'report_type': 'reportType',
    'rrd_id': 'rrdId',
    'gi_id': 'giId',
    'subject_name': 'subjectName',
    'nm_id': 'nmId',
    'brand_name': 'brandName',
    'sa_name': 'vendorCode',
    'ts_name': 'techSize',
    'barcode': 'sku',
    'doc_type_name': 'docTypeName',
    'quantity': 'quantity',
    'retail_price': 'retailPrice',
    'retail_amount': 'retailAmount',
    'sale_percent': 'salePercent',
    'commission_percent': 'commissionPercent',
    'office_name': 'officeName',
    'supplier_oper_name': 'sellerOperName',
    'order_dt': 'orderDt',
    'sale_dt': 'saleDt',
    'rr_dt': 'rrDate',
    'shk_id': 'shkId',
    'retail_price_withdisc_rub': 'retailPriceWithDisc',
    'delivery_amount': 'deliveryAmount',
    'return_amount': 'returnAmount',
    'delivery_rub': 'deliveryService',
    'product_discount_for_report': 'productDiscountForReport',
    'supplier_promo': 'sellerPromo',
    'ppvz_spp_prc': 'spp',
    'ppvz_kvw_prc_base': 'kvwBase',
    'ppvz_kvw_prc': 'kvw',
    'sup_rating_prc_up': 'supRatingUp',
    'is_kgvp_v2': 'isKgvpV2',
    'ppvz_sales_commission': 'ppvzSalesCommission',
    'ppvz_for_pay': 'forPay',
    'ppvz_reward': 'ppvzReward',
    'acquiring_fee': 'acquiringFee',
    'ppvz_vw': 'vw',
    'ppvz_vw_nds': 'vwNds',
    'ppvz_office_name': 'ppvzOfficeName',
    'bonus_type_name': 'bonusTypeName',
    'site_country': 'country',
    'penalty': 'penalty',
    'additional_payment': 'additionalPayment',
    'rebill_logistic_cost': 'rebillLogisticCost',
    'storage_fee': 'paidStorage',
    'deduction': 'deduction',
    'acceptance': 'paidAcceptance',
    'srid': 'srid',
}

_FLOAT_FIELDS = {
    'retail_price', 'retail_amount', 'commission_percent', 'retail_price_withdisc_rub', 'delivery_rub',
    'product_discount_for_report', 'supplier_promo', 'ppvz_spp_prc', 'ppvz_kvw_prc_base', 'ppvz_kvw_prc',
    'sup_rating_prc_up', 'is_kgvp_v2', 'ppvz_sales_commission', 'ppvz_for_pay', 'ppvz_reward',
    'acquiring_fee', 'ppvz_vw', 'ppvz_vw_nds', 'penalty', 'additional_payment', 'rebill_logistic_cost',
    'storage_fee', 'deduction', 'acceptance',
}

_INT_FIELDS = {
    'realizationreport_id', 'report_type', 'rrd_id', 'gi_id', 'nm_id', 'quantity', 'sale_percent',
    'shk_id', 'delivery_amount', 'return_amount',
}


def translate_sales_row(row):
    translated = {}
    for old_key, new_key in _SALES_FIELD_MAP.items():
        value = row.get(new_key)
        if old_key in _FLOAT_FIELDS:
            translated[old_key] = float(value) if value not in (None, '') else 0.0
        elif old_key in _INT_FIELDS:
            translated[old_key] = int(value) if value not in (None, '') else 0
        else:
            translated[old_key] = value if value is not None else ''
    return translated


# Ошибки API (ApiError/UnauthorizedError) намеренно не глушатся - их разбирает get_and_check_sales_report.
# Раньше здесь любая ошибка превращалась в пустой список, и отключение v5 неделю выглядело как "нет данных".
@with_session
async def get_sales_data(session, seller_id, date_from, date_to, rrdid, wb_api):
    body = {
        'dateFrom': date_from,
        'dateTo': date_to,
        'limit': SALES_PAGE_LIMIT,
        'rrdId': rrdid,
        'period': 'weekly',
    }
    async with ApiClient(db_session=session, seller_id=seller_id, api_key=wb_api) as client:
        batch = await client.fetch(method="POST",
                                   url=sales_url,
                                   headers={"Authorization": wb_api},
                                   json=body,
                                   timeout=120)

    # 204 (данных больше нет) приходит пустым телом
    if not batch:
        return []
    return [translate_sales_row(row) for row in batch]
