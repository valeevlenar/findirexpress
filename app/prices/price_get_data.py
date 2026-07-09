import asyncio
from app.prices.price_api_functions import unauthorised_price_api_identified
from app.prices.prices_wb_requests import get_goods_and_prices_from_wb, get_prices_api_for_seller_id
from app.wrappers import log_and_notify_admin

@log_and_notify_admin
async def get_goods_in_sale(session, seller_id):
    offset = 0
    goods_in_sale = []
    status = 'pending'
    # делаем первую выгрузку
    price_api = await get_prices_api_for_seller_id(session=session,
                                                   seller_id=seller_id)
    status_code, result = await get_goods_and_prices_from_wb(offset=offset,
                                                             price_api = price_api)
    # Защита: если get_goods_and_prices_from_wb упал с ошибкой и вернул None
    if not status_code:
        return 'error', goods_in_sale

    if status_code == 200:
        goods_in_sale+=result['data']['listGoods']
        # Проверяем, что строк меньше, чем 1000:
        if len(goods_in_sale) < 1000:
            status = 'done'
            return status, goods_in_sale
        elif len(goods_in_sale) >= 1000:
            offset +=len(goods_in_sale)
            while status != 'done':
                await asyncio.sleep(6)
                next_status_code, next_result = await get_goods_and_prices_from_wb(offset=offset,
                                                                                   price_api=price_api)
                if next_status_code==200:
                    goods_in_sale+=next_result['data']['listGoods']
                    if len(next_result['data']['listGoods'])<1000:
                        status = 'done'
                    else:
                        offset += len(next_result['data']['listGoods'])
                elif status_code == 401:
                    await unauthorised_price_api_identified(session=session,
                                                            seller_id=seller_id,
                                                            wb_api=price_api)
                    status = 'new_unauthorised_price_api'
                    return status, goods_in_sale
                else:
                    # Защита от бесконечного цикла при WB-глюках (500 и т.д.)
                    return 'error', goods_in_sale
    elif status_code ==401:
        await unauthorised_price_api_identified(session=session,
                                                seller_id=seller_id,
                                                wb_api=price_api)
        status = 'new_unauthorised_price_api'
        return status, goods_in_sale
    # result = pd.DataFrame(result)
    # result.to_excel('товары c ип.xlsx')
    return status, goods_in_sale



