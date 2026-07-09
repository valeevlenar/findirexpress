import requests
import logging

from app.admin.admin_message import send_message_to_admin
from app.database.api_functions import unauthorised_api_identified
from app.database.support_functions import get_api_by_seller_id
from app.wrappers import log_and_notify_admin, with_session


@with_session
async def get_goods_info_by_nm_id (session, seller_id, nm_id):
    try:
        get_goods_info_url = 'https://content-api.wildberries.ru/content/v2/get/cards/list'
        active_api = await get_api_by_seller_id(session=session, seller_id=seller_id)
        headers = {'Authorization': active_api}
        params = {
            "settings": {
                "sort": {"ascending": False},
                "filter": {
                    "allowedCategoriesOnly": False,
                    "imtID": 151494296,
                    "withPhoto": -1}}}

        res=requests.post(get_goods_info_url,headers=headers, json=params)
        result = res.json()
        # print(res.status_code)
        # print(res.text)
        if res.status_code == 200:
            pass
            # result_df = pd.DataFrame(result)
            # result_df.to_excel('заказы.xlsx')
            # try:
            #     result_df['order_date'] = pd.to_datetime(result_df.date).dt.normalize()+pd.Timedelta('23:59:59.999999')
            #     print(1)
            #     result_df['quantity'] = 1
            #     print(2)
            #     result_df.insert(0,'total_sum',result_df.pop('priceWithDisc'))
            #     print(3)
            #     result_df = result_df[['order_date','date','supplierArticle','nmId','barcode','category','subject','brand','techSize','quantity','total_sum']]
            #     print(4)
            #     result_grouped = result_df.groupby(['order_date','supplierArticle','nmId','barcode','category','subject','brand','techSize']).sum()
            #     print(5)
            #     orders_grouped_df = result_grouped.reset_index()
            #     print(6)
            #     orders_grouped_df.to_excel('заказы_обработанные.xlsx')
            #     return orders_grouped_df
            # except:
            #     print('что-то пошло не так в заказах')
            #     orders_grouped_df = None
            #     return orders_grouped_df
        elif res.status_code == 401:
                await unauthorised_api_identified(session=session, seller_id=seller_id,wb_api=active_api)
        else:
            await send_message_to_admin(f'Ошибка при получении баркодов по nm_id:'
                                        f'\nseller_id: {seller_id}')
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при получении баркодов по nm_id:'
                                    f'\nseller_id: {seller_id}'
                                    f'\nОшибка: {e}')
        logging.exception("An error occurred: %s", exc_info=e)