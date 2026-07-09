import logging

from app.database.classes.goods_cost_template import Goods_cost_template
from app.database.models import ApiKeys
from app.database.classes.stocks import Stock
from app.database.models import User, Seller, Goods_cost
from app.database.classes.sales import Sales
from sqlalchemy import select, func, case, and_, or_, update
import sqlalchemy.orm
import pandas as pd
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, Border, Side
from datetime import datetime
import app.main_bot.keyboards as kb
from app.database.support_functions import check_company_status, get_user_by_tg_id, get_seller_inn_by_seller_id
from app.get_data.marketing import save_and_allocate_reviews_payments_at_db
from app.user_communication.send_files_to_users import send_file_to_user
from app.main_bot.main_bot import bot
from app.wrappers import with_session, log_and_notify_admin


# Добавляем нового пользователя в базу
@with_session
async def set_user(session, data, tg_id,username):
    user = await session.scalar(select(User).where(User.tg_id == tg_id))
    if not user:
        new_user = User(tg_id=tg_id,
                                tg_username=username,
                                username=data["user_name"],
                                phone_number=data["user_phone_number"],
                                offer_approve=True,
                                date_created=datetime.now())
        session.add(new_user)
        # Используем flush вместо commit для получения ID
        await session.flush()

        new_user_id = new_user.id

        # Коммитим транзакцию
        await session.commit()
        # print(new_user_id)
        return new_user_id



# Добавление новой компании в базу:
@with_session
async def set_company(session, data, tg_id):
    user_id = await get_user_by_tg_id(session, tg_id)
    seller_type = 'company'
    seller_title = data["company_name"]
    if seller_title[:2]=='ИП':
        seller_type = 'ip'
    company = await session.scalar(select(Seller).where(Seller.seller_inn == data["inn"]))
    if not company:
        async with session.begin_nested():
            company=Seller(seller_title=data["company_name"],
                           seller_inn=data["inn"],
                           seller_type =seller_type,
                           tax_base=data["tax_base"],
                           tax_rate=float(str(data["tax_rate"]).replace("%","").replace(",","."))/100,
                               user_id=user_id,
                               user_tg_id=tg_id,
                               e_mail=data["e_mail"],
                               offer_signed=True,
                               balance=0,
                               first_cost_set=False,
                               first_reports_sent=False,
                               date_created=datetime.now(),
                               status="Active",
                               date_updated=datetime.now(),
                               service_status=True,
                               date_updated_ss=datetime.now(),
                               last_pl_calculated_date=None,
                               last_weekly_pl_sent_date=None,
                               last_monthly_pl_sent_date=None)
            session.add(company)
            await session.flush()
            seller_id = company.id
        await session.commit()
        async with session.begin_nested():
            session.add(ApiKeys(seller_id=seller_id,
                        wb_api=data["wb_api"],
                        api_date_created=datetime.now(),
                        api_status='active'))
        await session.commit()
        return seller_id

# проверяем, что по всем товарам заполнена себестоимость
@with_session
async def check_cost(session, seller_id):
    # Выгружаем все товары по селлеру из таблицы Goods cost и проверяем, что себестоимость не 0:
    goods = await session.execute(select(Goods_cost.barcode,
                                         Goods_cost.cost).
                                  where(Goods_cost.seller_id==seller_id))
    goods = goods.mappings().all()
    check = True
    for row in goods:
        cost = float(row['cost'])
        if cost<=0:
            check = False
        else:
            pass
# Если есть товары с нулевой с/с, то отправляем пользователю сообщение и шаблон:
    if check:
        return True
    else:
        if await Goods_cost_template.check_cost_template_sent_today(session=session, seller_id =seller_id):
            logging.info(f'Seller_id: {seller_id}. Шаблон уже отправлялся сегодня.')
            return False
        else:

            caption = (f'У Вас есть товары с нулевой или пустой себестоимостью.'
                       f'\nСкачайте шаблон для заполнения себестоимости, '
                       f'заполните его и отправьте нам.'
                       f'\nДля отправки нажмите кнопку '
                       f'"Загрузить шаблон с себестоимостью" в разделе "Себестоимость"')
            await get_cost_template(session=session, seller_id=seller_id,requestor_tg_id=None, caption=caption)
            return False

# формируем и отправляем пользователю шаблон для заполнения себестоимости
@with_session
async def get_cost_template(session, seller_id, requestor_tg_id, caption):
    if await check_company_status(session=session, seller_id=seller_id):
        query = (sqlalchemy.Select(Goods_cost.seller_inn.label('ИНН продавца'),
                                  Goods_cost.subject_name.label('Предмет'),
                                  Goods_cost.nm_id.label('Артикул ВБ'),
                                  Goods_cost.sa_name.label('Артикул продавца'),
                                  Goods_cost.barcode.label('Штрихкод'),
                                  Goods_cost.ts_name.label('Размер'),
                                  Goods_cost.cost.label('Себестоимость')).
                            where(Goods_cost.seller_id==seller_id))
        result=await session.execute(query)

        df = pd.DataFrame(result.all(), columns=result.keys())
        df.head()
        wb = Workbook()
        ws = wb.active
        for r in dataframe_to_rows(df, header=True, index=False):
            ws.append(r)
            for column in ws.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(cell.value)
                    except Exception as e:
                            # Запись ошибки в лог
                            logging.exception("An error occurred: %s", exc_info=e)
                adjusted_width = (max_length + 2)
                ws.column_dimensions[column_letter].width = adjusted_width
                ws.title='Себестоимость товаров'
        ft = Font(bold=True)
        thin = Side(border_style="thin", color="000000")
        for row in ws["A1:G1"]:
            for cell in row:
                cell.font = ft
                cell.border = Border(bottom=thin)
        company_name = await session.scalar(select(Seller.seller_title).where(Seller.id == seller_id))
        filename=f'{company_name}_шаблон для заполнения себестоимости.xlsx'
        if await send_file_to_user(session=session,
                                   bot=bot,
                                   seller_id=seller_id,
                                   file=wb,
                                   filename=filename,
                                   requestor_tg_id=requestor_tg_id,
                                   caption=caption):
            logging.info(f'Seller_id: {seller_id}. Отправлен шаблон с себестоимостью')
            await Goods_cost_template.cost_template_send(session = session,
                                                     seller_id= seller_id,
                                                     template_type='sent')
    else:pass

# получаем от пользователя шаблон с себестоимостью и обновляем себестоимость в базе
@with_session
async def set_new_cost_of_items(session, seller_id: int, costs_new, requestor_tg_id):
    chat_id = requestor_tg_id
    seller_inn = await get_seller_inn_by_seller_id(session=session, seller_id=seller_id)
    barcode_check = True
    # Нормализация ключей
    normalized_costs = []
    for item in costs_new:
        normalized = {k.strip().lower(): v for k, v in item.items()}
        normalized_costs.append(normalized)

    for item in normalized_costs:
        try:
            item_barcode = str(item['штрихкод'])
        except KeyError:
            await bot.send_message(chat_id, "Ошибка в файле: отсутствует столбец 'Штрихкод'")
            raise

    # print(seller_inn)
    for item in costs_new:
        item_barcode = str(item['Штрихкод'])
        # print (item_barcode)
        if item_barcode[0] == '0':
            item_barcode_without_zero = item_barcode[1:]
        else:
            item_barcode_without_zero = item_barcode
        item_inn = str(item['ИНН продавца'])
        item_cost_str = str(item['Себестоимость'])
        item_cost_str = item_cost_str.replace('\xa0', '').replace(' ', '').replace(',', '.')
        try:
            item_cost = float(item_cost_str)
        except ValueError as e:
            error_msg = f"Некорректное значение себестоимости: {item_cost_str}"
            logging.error(error_msg)
            raise ValueError(error_msg) from e

        if item_inn[0] == '0':
            item_inn_without_zero = item_inn[1:]
        else:
            item_inn_without_zero = item_inn

        if seller_inn[0] == '0':
            seller_inn_without_zero = seller_inn[1:]
        else:
            seller_inn_without_zero = seller_inn
        # print(item_barcode,item_inn,item_cost)
        if item_barcode != "" and (len(item_barcode)<=20) and item_cost>0 and seller_inn_without_zero==item_inn_without_zero:
            # print('пока ок')
            barcode_id = await session.scalar(
                select(Goods_cost.id).where(
                    case(
                        (func.substr(Goods_cost.barcode, 1, 1) == '0', func.substr(Goods_cost.barcode, 2)),
                        else_=Goods_cost.barcode
                    ) == item_barcode_without_zero,
                    Goods_cost.seller_id == seller_id
                )
            )

            if not barcode_id:
                barcode_check = False
            else:
                async with session.begin_nested():
                    query = sqlalchemy.update(Goods_cost).where(Goods_cost.id == barcode_id).values(cost=item_cost)
                    await session.execute(query)

                await session.commit()
        else:
            # print('не  ок')
            barcode_check = False
    if barcode_check:
        await Goods_cost_template.cost_template_upload(session=session, seller_id=seller_id, template_type='uploaded')
        return True
    else:
        await bot.send_message(chat_id,"В шаблоне есть ошибки. "
                                       "Исправьте ошибки, либо заново "
                                       "скачайте шаблон для заполнения "
                                       "себестоимости, заполните его и отправьте нам. "
                                        "\nДля отправки нажмите кнопку "
                                       "'Загрузить шаблон с себестоимостью'",
                               reply_markup=kb.main_kb(chat_id))
        raise ValueError("Ошибки в структуре шаблона")

# Выгружаем из таблицы Sales операции за период для обсчета себестоимости:
@with_session
async def set_pl_results(session, seller_id, date_start: datetime):
    try:
        tax_base= await session.scalar(select(Seller.tax_base).
                                        where(Seller.id==seller_id))
        tax_rate = await session.scalar(select(Seller.tax_rate).
                                        where(Seller.id == seller_id))

        sales_items = await session.execute(select(Sales.id,
                                                   Sales.seller_id,
                                                   Sales.seller_inn,
                                                   Sales.barcode,
                                                   Sales.transaction_date,
                                                   Sales.supplier_oper_name,
                                                   Sales.quantity,
                                                   Sales.bonus_type_name,
                                                   Sales.ppvz_for_pay,
                                                   Sales.storage_fee,
                                                   Sales.deduction,
                                                   Sales.rebill_logistic_cost,
                                                   Sales.acceptance,
                                                   Sales.penalty,
                                                   Sales.delivery_rub,
                                                   Sales.retail_amount,
                                                   Sales.retail_price,
                                                   Sales.doc_type_name).
                                            where(Sales.seller_id==seller_id,
                                                  Sales.transaction_date>=date_start))
        sales_items_df = pd.DataFrame(sales_items).to_dict('records')
        for sale_item in sales_items_df:
            # Отправляем транзакции в функцию расчета PL и занесения в базу:
            await set_pl_for_sale_item(session, seller_id, sale_item, tax_base, tax_rate)

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)
        await session.rollback()  # Откатываем транзакцию в случае ошибки
        raise

# Получаем транзакцию, расчитываем PL и обновляем в базе:
@log_and_notify_admin
async def set_pl_for_sale_item(session, seller_id, sale_item,tax_base, tax_rate):
    sales_id = sale_item['id']
    doc_type_name = sale_item['doc_type_name']
    supplier_oper_name = sale_item['supplier_oper_name']
    barcode=sale_item['barcode']
    retail_amount = sale_item['retail_amount']
    quantity = sale_item['quantity']
    ppvz_for_pay = sale_item['ppvz_for_pay']
    bonus_type_name = sale_item['bonus_type_name']
    storage_fee = sale_item['storage_fee']
    deduction = sale_item['deduction']
    rebill_logistic_cost = sale_item['rebill_logistic_cost']
    acceptance = sale_item['acceptance']
    penalty = sale_item['penalty']
    delivery_rub = sale_item['delivery_rub']
    retail_price = sale_item['retail_price']
    profit_before_tax = 0
    goods_quantity = 0
    revenue=0
    full_comission=0
    other_deductions = 0
    for_withdraw=0
    tax_base_amount = 0
    cost_of_sales = 0
    revenue_before_spp = 0
    commission_before_spp = 0
    spp_amount = 0

    # Перебираем все возможные варианты Обоснования для оплаты:
    if supplier_oper_name == "Продажа":
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id==seller_id,
                                                    Goods_cost.barcode == barcode))
        if sales_item_cos == None:
            revenue = retail_amount
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            revenue_before_spp = 0
            commission_before_spp = 0
            spp_amount = 0
        else:
            revenue=retail_amount
            cost_of_sales = -sales_item_cos*quantity
            full_comission = revenue - ppvz_for_pay
            goods_quantity = quantity
            revenue_before_spp = retail_price
            commission_before_spp = revenue_before_spp - ppvz_for_pay
            spp_amount = retail_price - retail_amount
        # Считаем сумму к выводу:
        for_withdraw = (revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)
    elif supplier_oper_name == "Возврат":
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id==seller_id,
                                                    Goods_cost.barcode == barcode))
        if sales_item_cos == None:
            revenue=-retail_amount
            cost_of_sales = 0
            revenue_before_spp = -retail_price
            commission_before_spp = -(revenue_before_spp - ppvz_for_pay)
            spp_amount = -(retail_price - retail_amount)
        else:
            cost_of_sales = sales_item_cos*quantity
            revenue = -retail_amount
            full_comission = -(retail_amount - ppvz_for_pay)
            goods_quantity = -quantity
            revenue_before_spp = -retail_price
            commission_before_spp = -(retail_price - ppvz_for_pay)
            spp_amount = -(retail_price - retail_amount)

        # Считаем сумму к выводу:
        for_withdraw = (
                    revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)

    # Обрабатываем компенсацию ущерба:
    elif supplier_oper_name == "Компенсация ущерба" and (doc_type_name == 'Продажа' or doc_type_name == ''):
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id==seller_id,
                                                    Goods_cost.barcode == barcode))
        if (sales_item_cos == None):
            revenue = retail_amount
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            revenue_before_spp = retail_price
            commission_before_spp = (revenue_before_spp - ppvz_for_pay)
            spp_amount = (retail_price - retail_amount)
        else:
            revenue = ppvz_for_pay
            cost_of_sales = -sales_item_cos*quantity
            full_comission = 0
            goods_quantity = quantity
            revenue_before_spp = ppvz_for_pay
            commission_before_spp = 0
            spp_amount = 0


        # Считаем сумму к выводу:
        for_withdraw = (
                    revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)

    elif supplier_oper_name == "Компенсация ущерба" and doc_type_name == 'Возврат':
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id==seller_id,
                                                    Goods_cost.barcode == barcode))
        if (sales_item_cos == None):
            revenue = -retail_amount
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            revenue_before_spp = -retail_price
            commission_before_spp = -(revenue_before_spp - ppvz_for_pay)
            spp_amount = -(retail_price - retail_amount)
        else:
            revenue = -ppvz_for_pay
            cost_of_sales = sales_item_cos*quantity
            full_comission = 0
            goods_quantity = -quantity
            revenue_before_spp = -ppvz_for_pay
            commission_before_spp = 0
            spp_amount = 0


        # Считаем сумму к выводу:
        for_withdraw = (
                    revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)

    # Обрабатываем корректировку эквайринга:
    elif supplier_oper_name == "Корректировка эквайринга":
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id==seller_id,
                                                    Goods_cost.barcode == barcode))
        if sales_item_cos == None:
            revenue = retail_amount
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            revenue_before_spp = 0
            commission_before_spp = 0
            spp_amount = 0
        else:
            revenue=0
            cost_of_sales = -sales_item_cos*quantity
            full_comission = -ppvz_for_pay
            goods_quantity = quantity
            revenue_before_spp = 0
            commission_before_spp = -ppvz_for_pay
            spp_amount = 0
        # Считаем сумму к выводу:
        for_withdraw = (
                    revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)
        # Обрабатываем корректировку эквайринга:
    elif supplier_oper_name == "Коррекция продаж":
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id == seller_id,
                                                    Goods_cost.barcode == barcode))
        if sales_item_cos == None:
            revenue = retail_amount
            cost_of_sales = 0
            full_comission = -ppvz_for_pay
            goods_quantity = 0
            revenue_before_spp = retail_price
            commission_before_spp = - ppvz_for_pay
            spp_amount = retail_price - retail_amount

        else:
            revenue = retail_amount
            cost_of_sales = 0
            full_comission = -ppvz_for_pay
            goods_quantity = 0
            revenue_before_spp = retail_price
            commission_before_spp = - ppvz_for_pay
            spp_amount = retail_price - retail_amount

        # Считаем сумму к выводу:
        for_withdraw = (
                revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)

    # Обрабатываем корректировку эквайринга:
    elif supplier_oper_name == "Добровольная компенсация при возврате":
        sales_item_cos = await session.scalar(select(Goods_cost.cost).
                                              where(Goods_cost.seller_id == seller_id,
                                                    Goods_cost.barcode == barcode))
        if sales_item_cos == None:
            revenue = ppvz_for_pay
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            revenue_before_spp = ppvz_for_pay
            commission_before_spp = 0
            spp_amount = 0

        else:
            revenue = ppvz_for_pay
            cost_of_sales = -sales_item_cos * quantity
            full_comission = 0
            goods_quantity = quantity
            revenue_before_spp = ppvz_for_pay
            commission_before_spp = 0
            spp_amount = 0

        # Считаем сумму к выводу:
        for_withdraw = (
                revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)
    # Обрабатываем удержания по маркетингу:

    elif supplier_oper_name == "Удержание":
        if 'Оказание услуг «WB Продвижение»' in bonus_type_name:
            revenue = 0
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            for_withdraw = (revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)
            profit_before_tax = 0
            revenue_before_spp = 0
            commission_before_spp = 0
            spp_amount = 0
        elif 'Списание за отзыв' in bonus_type_name or 'Аванс за услугу "Баллы за отзывы"' in bonus_type_name:
            await save_and_allocate_reviews_payments_at_db(session=session, seller_id=seller_id, sales_item=sale_item)
            revenue = 0
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            for_withdraw = (revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)
            profit_before_tax = 0
            revenue_before_spp = 0
            commission_before_spp = 0
            spp_amount = 0
        else:
            revenue = 0
            cost_of_sales = 0
            full_comission = 0
            goods_quantity = 0
            other_deductions = deduction
            for_withdraw = (revenue - full_comission - acceptance - other_deductions - storage_fee - penalty - delivery_rub)
            profit_before_tax = for_withdraw + cost_of_sales
            revenue_before_spp = 0
            commission_before_spp = 0
            spp_amount = 0
    else:
        # Считаем сумму к выводу:
        for_withdraw = (revenue - full_comission - acceptance - deduction - storage_fee - penalty - delivery_rub)

        # Считаем прибыль до налогообложения:
        profit_before_tax = (for_withdraw + cost_of_sales)

    # Считаем налоги в зависимости от базы:
    if tax_base=="income":
        tax_base_amount = revenue
    elif tax_base=="income_less_exp":
        tax_base_amount = profit_before_tax
    else:
        print("Где-то ошибка в расчете налогов")

    tax_costs = -tax_base_amount*tax_rate

    #Считаем прибыль по строке
    net_profit = profit_before_tax+tax_costs

    await update_pl_results(session,
                            sales_id,
                            goods_quantity,
                            revenue,
                            full_comission,
                            other_deductions,
                            for_withdraw,
                            cost_of_sales,
                            tax_base_amount,
                            tax_costs,
                            net_profit,
                            revenue_before_spp,
                            commission_before_spp,
                            spp_amount)

# заполняем посчитанные фин. результаты в базе построчно:
@log_and_notify_admin
async def update_pl_results(session,
                            sales_id,
                            goods_quantity,
                            revenue,
                            full_comission,
                            other_deductions,
                            for_withdraw,
                            cost_of_sales,
                            tax_base_amount,
                            tax_costs,
                            net_profit,
                            revenue_before_spp,
                            commission_before_spp,
                            spp_amount):
    async with session.begin_nested():
        query = (sqlalchemy.update(Sales).
                 where(Sales.id == sales_id).
                 values(goods_quantity=goods_quantity,
                        revenue=revenue,
                        full_comission=full_comission,
                        other_deductions = other_deductions,
                        for_withdraw=for_withdraw,
                        cost_of_sales=cost_of_sales,
                        tax_base_amount=tax_base_amount,
                        tax_costs=tax_costs,
                        net_profit=net_profit,
                        revenue_before_spp = revenue_before_spp,
                        commission_before_spp = commission_before_spp,
                        spp_amount = spp_amount
                        ))
        await session.execute(query)
    await session.commit()

# заполняем себестоимость в таблице с остатками:
@with_session
async def set_cost_to_stock(session, seller_id, date_start: datetime):
    try:
        # 1. Получаем все себестоимости селлера РАЗОМ и кладем в словарь {barcode: cost}
        # Это избавит нас от тысяч SELECT-запросов в цикле!
        costs_result = await session.execute(
            select(Goods_cost.barcode, Goods_cost.cost)
            .where(Goods_cost.seller_id == seller_id)
        )
        cost_map = {row.barcode: float(row.cost or 0.0) for row in costs_result}

        # 2. Получаем остатки.
        # Добавили условие: ИЛИ дата >= date_start, ИЛИ себестоимость пустая/нулевая (для истории)
        stock_items = await session.execute(
            select(Stock.id, Stock.barcode, Stock.quantityfull)
            .where(
                Stock.seller_id == seller_id,
                or_(
                    Stock.date_in_stock >= date_start,
                    Stock.cost_per_item.is_(None),
                    Stock.cost_per_item == 0
                )
            )
        )

        # 3. Подготавливаем данные для массового апдейта
        update_data = []
        for row in stock_items.all():
            barcode = str(row.barcode)
            # Исправлена ошибка регистра: quantityfull с маленькой буквы
            quantity = float(row.quantityfull or 0.0)

            # Берем себестоимость из словаря (если баркода нет, подставит 0.0)
            cost_per_item = cost_map.get(barcode, 0.0)
            total_at_cost = cost_per_item * quantity

            update_data.append({
                "id": row.id,  # Обязательно передаем Primary Key для массового update в SQLAlchemy
                "cost_per_item": cost_per_item,
                "total_at_cost": total_at_cost
            })

        # 4. Массово обновляем БД (пачками по 1000 строк)
        if update_data:
            chunk_size = 1000
            for i in range(0, len(update_data), chunk_size):
                chunk = update_data[i:i + chunk_size]
                # SQLAlchemy 2.0 позволяет передавать список словарей в execute() для массового UPDATE
                await session.execute(update(Stock), chunk)

            await session.commit()
            logging.info(
                f"Seller_id: {seller_id}. Успешно обновлена себестоимость для {len(update_data)} записей остатков.")
        else:
            logging.info(f"Seller_id: {seller_id}. Нет записей остатков для обновления себестоимости.")

    except Exception as e:
        await session.rollback()
        logging.exception("An error occurred in set_cost_to_stock: %s", exc_info=e)
