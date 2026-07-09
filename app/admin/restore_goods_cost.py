from app.admin.admin_message import send_message_to_admin
from app.database.classes.sales import Sales
from app.database.classes.stocks import Stock
from app.database.models import Goods_cost, Orders
from app.wrappers import with_session
from sqlalchemy import select
import sqlalchemy
import pandas as pd


@with_session
async def restore_goods_cost(session):
    barcodes = await session.execute(select(Goods_cost.barcode,
                                            Goods_cost.seller_id).
                                     where(Goods_cost.cost==0))
    barcodes_list = barcodes.mappings().all()
    # print(len(barcodes_list))

    barcodes_costs = []
    updated = 0
    for item in barcodes_list:
        barcode = item['barcode']
        seller_id = item['seller_id']

        barcode_cost = await session.scalar(select(Sales.cost_of_sales / Sales.goods_quantity).
                                            where(Sales.cost_of_sales != 0,
                                                  Sales.barcode == barcode,
                                                  Sales.seller_id == seller_id).
                                            order_by(Sales.transaction_date.desc())) or 0

        if barcode_cost != 0:
            barcodes_costs.append({'seller_id': seller_id,
                                   'barcode': barcode,
                                   'cost': abs(barcode_cost)})

            try:
                async with session.begin_nested():
                    query = sqlalchemy.update(Goods_cost).where(Goods_cost.barcode == barcode,
                                                                Goods_cost.seller_id==seller_id).values(cost=barcode_cost)
                    await session.execute(query)

                await session.commit()
                updated +=1
            except:
                await send_message_to_admin(f'Не удалось сделать')

    await send_message_to_admin(f'Всего пустых баркодов: {len(barcodes_list)}'
                                f'\nНайдено себестоимости: {len(barcodes_costs)}'
                                f'\nОбновили себестоимости: {updated}')
    print(len(barcodes_costs))
    print(barcodes_costs)
    barcodes_costs_df = pd.DataFrame(barcodes_costs)
    # df.to_csv('продажи_все.csv')
    barcodes_costs_df.to_excel('себестоимость по баркодам.xlsx')

@with_session
async def restore_goods_cost2(session):
    barcodes = await session.execute(select(Goods_cost.barcode,
                                            Goods_cost.seller_id).
                                     where(Goods_cost.subject_name==0))
    barcodes_list = barcodes.mappings().all()
    # print(len(barcodes_list))

    barcodes_costs = []
    updated = 0
    for item in barcodes_list:
        barcode = item['barcode']
        seller_id = item['seller_id']

        barcode_cost = await session.scalar(select(Stock.cost_per_item).
                                            where(Stock.cost_per_item != 0,
                                                  Stock.barcode == barcode,
                                                  Stock.seller_id == seller_id).
                                            order_by(Stock.date_in_stock.desc())) or 0

        if barcode_cost != 0:
            barcodes_costs.append({'seller_id': seller_id,
                                   'barcode': barcode,
                                   'cost': abs(barcode_cost)})

            try:
                async with session.begin_nested():
                    query = sqlalchemy.update(Goods_cost).where(Goods_cost.barcode == barcode,
                                                                Goods_cost.seller_id==seller_id).values(cost=abs(barcode_cost))
                    await session.execute(query)

                await session.commit()
                updated +=1
            except:
                await send_message_to_admin(f'Не удалось сделать')

    await send_message_to_admin(f'Всего пустых баркодов: {len(barcodes_list)}'
                                f'\nНайдено себестоимости: {len(barcodes_costs)}'
                                f'\nОбновили себестоимости: {updated}')
    print(len(barcodes_costs))
    print(barcodes_costs)
    barcodes_costs_df = pd.DataFrame(barcodes_costs)
    # df.to_csv('продажи_все.csv')
    barcodes_costs_df.to_excel('себестоимость по баркодам.xlsx')


@with_session
async def restore_goods_cost_names(session):
    """
    Восстанавливает отсутствующие названия, артикулы, размеры и бренды для товаров
    в таблице Goods_cost, извлекая их из таблицы Stock.
    """
    # 1. Находим все товары в Goods_cost, где название темы (subject_name) пустое.
    barcodes_query = select(Goods_cost.barcode, Goods_cost.seller_id).where(Goods_cost.subject_name == '')
    barcodes_result = await session.execute(barcodes_query)
    barcodes_list = barcodes_result.mappings().all()

    updated_count = 0
    total_count = len(barcodes_list)

    await send_message_to_admin(f'Начинаем восстановление. Всего пустых записей: {total_count}')

    # 2. Итерируемся по списку товаров с пустыми названиями.
    for item in barcodes_list:
        barcode = item['barcode']
        seller_id = item['seller_id']

        # 3. Для каждого товара ищем соответствующие данные в таблице Stock.
        stock_data_query = (
            select(Stock.subject, Stock.supplier_article, Stock.techsize, Stock.brand)
            .where(Stock.barcode == barcode, Stock.seller_id == seller_id)
            .group_by(Stock.subject, Stock.supplier_article, Stock.techsize, Stock.brand)
            .limit(1) # Добавляем limit(1), так как нам нужна только одна запись для обновления.
        )
        stock_data_result = await session.execute(stock_data_query)
        barcodes_data = stock_data_result.mappings().all()

        # ИЗМЕНЕНИЕ: Проверяем, что список barcodes_data не пуст.
        # Раньше было `if barcodes_data != 0`, что не является идиоматичным для Python.
        if barcodes_data:
            # ИЗМЕНЕНИЕ: Так как barcodes_data - это список, мы берем первый элемент [0].
            # Это исправляет ошибку TypeError.
            data_row = barcodes_data[0]

            subject_name = data_row['subject']
            article = data_row['supplierArticle']
            size = data_row['techSize']
            brand = data_row['brand']

            try:
                # 4. Обновляем запись в Goods_cost.
                # Использование begin_nested() здесь хорошо подходит для обеспечения атомарности
                # обновления каждой отдельной записи.
                async with session.begin_nested():
                    update_query = (
                        sqlalchemy.update(Goods_cost)
                        .where(Goods_cost.barcode == barcode, Goods_cost.seller_id == seller_id)
                        .values(
                            subject_name=subject_name,
                            sa_name=article,
                            ts_name=size,
                            brand=brand
                        )
                    )
                    await session.execute(update_query)
                await session.commit()

                updated_count += 1
            except Exception as e:
                # Лучше логировать ошибку, чтобы понимать, что пошло не так.
                print(f"Не удалось обновить barcode {barcode} для seller_id {seller_id}. Ошибка: {e}")
                await send_message_to_admin(f'Не удалось обновить barcode {barcode}. Ошибка: {e}')
        if not barcodes_data:
            orders_data_query = (
                select(Orders.subject, Orders.supplier_article, Orders.techsize, Orders.brand)
                .where(Orders.barcode == barcode, Orders.seller_id == seller_id)
                .group_by(Orders.subject, Orders.supplier_article, Orders.techsize, Orders.brand)
                .limit(1)  # Добавляем limit(1), так как нам нужна только одна запись для обновления.
            )
            stock_data_result = await session.execute(orders_data_query)
            barcodes_data = stock_data_result.mappings().all()

            # ИЗМЕНЕНИЕ: Проверяем, что список barcodes_data не пуст.
            # Раньше было `if barcodes_data != 0`, что не является идиоматичным для Python.
            if barcodes_data:
                # ИЗМЕНЕНИЕ: Так как barcodes_data - это список, мы берем первый элемент [0].
                # Это исправляет ошибку TypeError.
                data_row = barcodes_data[0]

                subject_name = data_row['subject']
                article = data_row['supplierArticle']
                size = data_row['techSize']
                brand = data_row['brand']

                try:
                    # 4. Обновляем запись в Goods_cost.
                    # Использование begin_nested() здесь хорошо подходит для обеспечения атомарности
                    # обновления каждой отдельной записи.
                    async with session.begin_nested():
                        update_query = (
                            sqlalchemy.update(Goods_cost)
                            .where(Goods_cost.barcode == barcode, Goods_cost.seller_id == seller_id)
                            .values(
                                subject_name=subject_name,
                                sa_name=article,
                                ts_name=size,
                                brand=brand
                            )
                        )
                        await session.execute(update_query)
                    await session.commit()

                    updated_count += 1
                except Exception as e:
                    # Лучше логировать ошибку, чтобы понимать, что пошло не так.
                    print(f"Не удалось обновить barcode {barcode} для seller_id {seller_id}. Ошибка: {e}")
                    await send_message_to_admin(f'Не удалось обновить barcode {barcode}. Ошибка: {e}')

    # 5. Отправляем итоговый отчет администратору.
    # commit() скорее всего вызывается в декораторе with_session, но если нет, его нужно добавить.
    # await session.commit() # Раскомментируйте, если декоратор не делает commit.

    await send_message_to_admin(
        f'Восстановление завершено.\n'
        f'Всего было пустых баркодов: {total_count}\n'
        f'Обновлено названий: {updated_count}'
    )

