from datetime import datetime
import logging
from app.admin.admin_message import send_message_to_admin
import requests
import os.path

from app.database.support_functions import get_seller_inn_by_seller_id, get_seller_type_by_seller_id, \
    get_company_name_by_seller_id
from app.wrappers import with_session, log_and_notify_admin
from config import account_id, customer_code, bank_token, create_invoice_url, create_closing_doc_url, \
    get_invoice_from_bank_url, check_invoice_status_url, get_closing_document_from_bank_url, invoice_folder, \
    closing_documents_folder


def _bank_integration_disabled():
    if not bank_token:
        logging.info('Интеграция с банком Точка отключена (не задан JWTTOKEN в .env) - пропускаем вызов.')
        return True
    return False


@log_and_notify_admin
async def create_new_invoice_in_bank(session, seller_id, invoice_id, subscription_duration, amount, invoice_number):
    if _bank_integration_disabled():
        return None
    try:
        headers = {'Authorization': f'Bearer {bank_token}'}
        seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
        seller_type = await get_seller_type_by_seller_id(session, seller_id)
        seller_title = await get_company_name_by_seller_id(session, seller_id)
        invoice_number=invoice_number
        # invoice_number = await get_invoice_number_by_invoice_id(invoice_id)
        # subscription_duration = await get_subscription_duration_by_invoice_id(invoice_id)
        invoice_text = f'Подписка на сервис ФиндирЭкспресс "{subscription_duration} мес.". Без НДС.'
        amount = amount
        # amount = str(await get_invoice_amount_by_invoice_id(invoice_id))
        invoice_data = {"Data":{"accountId": account_id,
                        "customerCode": customer_code,
                        "SecondSide": {
                            "taxCode": seller_inn,
                            "type": seller_type,
                            "secondSideName": seller_title},
                        "Content": {
                            "Invoice": {
                                "Positions": [
                                    {"positionName": invoice_text,
                                     "unitCode": "услуга.",
                                     "ndsKind": "without_nds",
                                     "price": amount,
                                     "quantity": "1",
                                     "totalAmount": amount,
                                     "totalNds": "0"}],
                                "totalAmount": amount,
                                "totalNds": "0",
                                "number": invoice_number
                                       }}}}
        # print(invoice_data)
        res=requests.post(create_invoice_url,headers=headers, json=invoice_data)
        json=res.json()
        # print(res.status_code)
        # print(res.text)
        bank_invoice_id = ''
        if res.status_code == 200:
            data = json['Data']
            bank_invoice_id = data['documentId']
            return bank_invoice_id
        else:
            await send_message_to_admin(text=f'Ошибка при генерации счета в банке'
                                             f'\nSeller_id: {seller_id}'
                                             f'\nInvoice_id: {invoice_id}'
                                             f'\nres: {res.text}')
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при генерации счета в банке'
                                         f'\nSeller_id: {seller_id}'
                                         f'\nInvoice_id: {invoice_id}'
                                    f'\n{e}')
        logging.exception("An error occurred: %s", exc_info=e)

    # print(res.status_code)
    # print(res.text)

# Скачиваем счет из банка
@log_and_notify_admin
async def get_invoice_from_bank(session, seller_id, invoice_number, invoice_id, bank_invoice_id):
    if _bank_integration_disabled():
        return None
    try:
        headers = {'Authorization': f'Bearer {bank_token}'}
        get_invoice_from_bank_route = f'{get_invoice_from_bank_url}{customer_code}/{bank_invoice_id}/file'
        res = requests.get(get_invoice_from_bank_route,headers=headers)
        folder_name = invoice_folder
        seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
        seller_title = await get_company_name_by_seller_id(session, seller_id)
        seller_title = seller_title.replace('"','')
        file_name = f'{seller_inn}_{seller_title}_{invoice_number}.pdf'
        complete_name = os.path.join(folder_name, file_name)
        if res.status_code ==200:
            # print(res.status_code)
            # print(res.headers['content-type'])
            # print(res.headers['content-disposition'])
            invoice_file = open(complete_name, 'wb')
            invoice_file.write(res.content)



            return file_name, res
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при скачивании счета из банка'
                                         f'{e}')
        logging.exception("An error occurred: %s", exc_info=e)

async def check_invoice_status(bank_invoice_id):
    if _bank_integration_disabled():
        return None
    try:
        headers = {'Authorization': f'Bearer {bank_token}'}
        url = f'{check_invoice_status_url}{customer_code}/{bank_invoice_id}/payment-status'
        res = requests.get(url,headers=headers)
        # print(res.status_code)
        # print(res.json())
        if res.status_code==200:
            result = res.json()
            # print(result['Data']['paymentStatus'])
            return result['Data']['paymentStatus']
        # not_paid_status = 'payment_waiting'
        # paid_status = 'payment_paid'
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при проверке статуса счета в банке'
                                         f'{e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def create_closing_document_in_bank(session, seller_id, amount, date_start, date_end, closing_document_number ):
    if _bank_integration_disabled():
        return None
    try:
        headers = {'Authorization': f'Bearer {bank_token}'}
        seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
        seller_type = await get_seller_type_by_seller_id(session, seller_id)
        seller_title = await get_company_name_by_seller_id(session, seller_id)
        date_start_str = datetime.strftime(date_start,'%d.%m.%Y')
        date_end_str = datetime.strftime(date_end, '%d.%m.%Y')
        closing_document_text = f'Предоставление отчетов сервиса "ФиндирЭкспресс" по подписке за период с {date_start_str} г. по {date_end_str} г.'
        date_end_str_for_doc = datetime.strftime(date_end, '%Y-%m-%d')
        closing_document_data = {"Data":
                                     {"accountId": account_id,
                                      "customerCode": customer_code,
                                      "SecondSide": {
                                          "taxCode": seller_inn,
                                          "type": seller_type,
                                          "secondSideName": seller_title},
                                      "Content": {"Act": {
                                          "Positions": [{
                                              "positionName": closing_document_text,
                                              "unitCode": "услуга.",
                                              "ndsKind": "without_nds",
                                              "price": amount,
                                              "quantity": "1",
                                              "totalAmount": amount,
                                              "totalNds": "0"
                                          }],
                                          "date": date_end_str_for_doc,
                                          "totalAmount": amount,
                                          "totalNds": "0",
                                          "number": closing_document_number}}}}

        res=requests.post(create_closing_doc_url,headers=headers, json=closing_document_data)
        json=res.json()
        bank_closing_doc_id = ''
        if res.status_code == 200:
            data = json['Data']
            bank_closing_doc_id = data['documentId']
            return bank_closing_doc_id
        else:
            await send_message_to_admin(text=f'Ошибка при генерации закрывающего документа в банке'
                                             f'\nSeller_id: {seller_id}'
                                             f'\nClosing_doc_number: {closing_document_number}')
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при генерации закрывающего документа в банке'
                                         f'\nSeller_id: {seller_id}'
                                         f'\nClosing_doc_number: {closing_document_number}'
                                        f'\n{e}')
        logging.exception("An error occurred: %s", exc_info=e)

    # Скачиваем закрывающий документ из банка

@log_and_notify_admin
async def get_closing_document_from_bank(session, seller_id, closing_document_number, closing_document_tochka_doc_id):
    if _bank_integration_disabled():
        return None
    try:
        # print(closing_document_tochka_doc_id)
        headers = {'Authorization': f'Bearer {bank_token}'}
        get_closing_document_from_bank_route = f'{get_closing_document_from_bank_url}{customer_code}/{closing_document_tochka_doc_id}/file'
        res = requests.get(get_closing_document_from_bank_route, headers=headers)
        folder_name = closing_documents_folder
        seller_inn = await get_seller_inn_by_seller_id(session, seller_id)
        seller_title = await get_company_name_by_seller_id(session, seller_id)
        seller_title = seller_title.replace('"', '')
        file_name = f'Акт_{seller_inn}_{seller_title}_{closing_document_number}.pdf'
        complete_name = os.path.join(folder_name, file_name)
        if res.status_code == 200:
            # print(res.status_code)
            # print(res.headers['content-type'])
            # print(res.headers['content-disposition'])
            closing_document_file = open(complete_name, 'wb')
            closing_document_file.write(res.content)
            return file_name, res
    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(text=f'Ошибка при скачивании счета из банка'
                                         f'\n{e}')
        logging.exception("An error occurred: %s", exc_info=e)


    # print(res.status_code)
    # print(res.text)

# def get_customers_list():
#     url = "https://enter.tochka.com/uapi/open-banking/v1.0/customers"
#     payload = {}
#     headers = {
#     'Authorization': f'Bearer {bank_token}'
#     }
#     response = requests.request("GET", url, headers=headers, data=payload)
#     print(response.text)
#
# get_customers_list()