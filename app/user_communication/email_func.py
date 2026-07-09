import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.mime.base import MIMEBase
from email import encoders
from sqlalchemy.testing.plugin.plugin_base import logging
import config
from app.admin.admin_message import send_message_to_admin
from app.database.models import Reports
from app.database.support_functions import get_email_by_seller_id, get_company_name_by_seller_id, \
    get_seller_inn_by_seller_id
from datetime import datetime
from dotenv import load_dotenv

from app.wrappers import with_session, log_and_notify_admin

load_dotenv()

from_mail =  config.FROM_MAIL                  # Почта отправителя
from_passwd = os.getenv("yandex_password")                # пароль от почты отправителя
server_adr = config.SERVER_ADR                            # адрес почтового сервера
server_port = config.SERVER_PORT

@log_and_notify_admin
async def send_report_via_email(session, seller_id, report_type, report_creation_type, file_to_send, filename, date_from, date_to): # файл должен быть в формате file_in_io.getvalue()
    email_to = await get_email_by_seller_id(session=session, seller_id=seller_id)               # берем адрес почты из базы компаний
    company_name = await get_company_name_by_seller_id(session=session, seller_id=seller_id)
    try:
        # Создание объекта сообщения
        date_to_str = datetime.strftime(date_to,'%Y-%m-%d')
        date_from_str = datetime.strftime(date_from, '%Y-%m-%d')
        report_type_str=""
        if report_type == "weekly":
            report_type_str = "Еженедельный"
        elif report_type == "monthly":
            report_type_str = "Ежемесячный"
        msg = MIMEMultipart()

        # Добавление текста в сообщение:
        msg_text = (f'Добрый день!\n'
                    f'\nНаправляем Вам {report_type_str} отчет по результатам торговли на ВБ!\n'
                    f'\nК письму приложен документ для {company_name} от ООО "ФиндирЭкспресс":'
                    f'\n-Отчет о финансовых результатах за период с {date_from_str} по {date_to_str}.'
                    f'\n\nС уважением, команда ФиндирЭкспресс❤️')

        # Настройка сообщения:
        msg["Subject"] = Header(f'{report_type_str} отчет по ВБ 📧"', "utf-8")
        msg["From"] = from_mail
        msg["To"] = email_to
        msg.attach(MIMEText(msg_text, "plain", 'utf-8'))
        part = MIMEBase('application', "octet-stream")  # Создаем объект для загрузки файла
        part.set_payload(file_to_send)  # Подключаем файл
        encoders.encode_base64(part)
        part.add_header('content-disposition', 'attachment', filename=filename)
        msg.attach(part)

        # Подключаемся к почте и отправляем сообщение:
        server = smtplib.SMTP(host=server_adr, port=server_port)
        server.starttls()
        server.login(user=from_mail,password=from_passwd)
        server.sendmail(from_addr=msg["From"], to_addrs=[msg["To"],msg['From']], msg=msg.as_string())
        server.quit()



    except Exception as e:
        # Запись ошибки в лог
        await send_message_to_admin(f'Ошибка при отправке отчета:'
                                    f'\n{e}')
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def add_report_delivery_to_db(session, seller_id, report_type, report_creation_type, date_to, user_id):
    async with session.begin_nested():
        session.add(Reports(seller_id=seller_id,
                            seller_inn=await get_seller_inn_by_seller_id(session=session, seller_id=seller_id),
                            report_type=report_type,
                            report_creation_type=report_creation_type,
                            report_date_to=date_to,
                            report_status="sent",
                            created_at=datetime.now(),
                            user_id=user_id))
    await session.commit()

@log_and_notify_admin
async def send_invoice_via_email(session, seller_id, file_to_send, filename): # файл должен быть в формате file_in_io.getvalue()
    email_to = await get_email_by_seller_id(session=session, seller_id=seller_id)               # берем адрес почты из базы компаний
    try:
        # Создание объекта сообщения
        msg = MIMEMultipart()

        # Добавление текста в сообщение:
        msg_text = (f'Добрый день!\n'
                    f'\nНаправляем Вам счет на оплату подписки на сервис ФиндирЭкспресс.\n'
                    
                    f'\n\nС уважением, команда ФиндирЭкспресс❤️')

        # Настройка сообщения:
        msg["Subject"] = Header(f'Счет на оплату подписки ФиндирЭкспресс 📧"', "utf-8")
        msg["From"] = from_mail
        msg["To"] = email_to
        msg.attach(MIMEText(msg_text, "plain", 'utf-8'))
        part = MIMEBase('application', "octet-stream")  # Создаем объект для загрузки файла
        part.set_payload(file_to_send)  # Подключаем файл
        encoders.encode_base64(part)
        part.add_header('content-disposition', 'attachment', filename=filename)
        msg.attach(part)

        # Подключаемся к почте и отправляем сообщение:
        server = smtplib.SMTP(host=server_adr, port=server_port)
        server.starttls()
        server.login(user=from_mail,password=from_passwd)
        server.sendmail(from_addr=msg["From"], to_addrs=[msg["To"],msg['From']], msg=msg.as_string())
        server.quit()

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)

@log_and_notify_admin
async def send_closing_document_via_email(session, seller_id, file_to_send, filename,date_start_str, date_end_str):  # файл должен быть в формате file_in_io.getvalue()
    email_to = await get_email_by_seller_id(session=session, seller_id=seller_id)  # берем адрес почты из базы компаний
    try:
        # Создание объекта сообщения
        msg = MIMEMultipart()

        # Добавление текста в сообщение:
        msg_text = (f'Добрый день!\n'
                    f'\nНаправляем Вам акт об оказанных услугах '
                    f'ООО "ФиндирЭкспресс" за период с {date_start_str} г. по {date_end_str} г.\n'

                    f'\n\nС уважением, команда ФиндирЭкспресс❤️')

        # Настройка сообщения:
        msg["Subject"] = Header(f'Акт об оказанных услугах ФиндирЭкспресс 📧"', "utf-8")
        msg["From"] = from_mail
        msg["To"] = email_to
        msg.attach(MIMEText(msg_text, "plain", 'utf-8'))
        part = MIMEBase('application', "octet-stream")  # Создаем объект для загрузки файла
        part.set_payload(file_to_send)  # Подключаем файл
        encoders.encode_base64(part)
        part.add_header('content-disposition', 'attachment', filename=filename)
        msg.attach(part)

        # Подключаемся к почте и отправляем сообщение:
        server = smtplib.SMTP(host=server_adr, port=server_port)
        server.starttls()
        server.login(user=from_mail, password=from_passwd)
        server.sendmail(from_addr=msg["From"], to_addrs=[msg["To"], msg['From']], msg=msg.as_string())
        server.quit()

    except Exception as e:
        # Запись ошибки в лог
        logging.exception("An error occurred: %s", exc_info=e)






