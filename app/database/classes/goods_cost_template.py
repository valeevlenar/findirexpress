from datetime import datetime
from sqlalchemy import ForeignKey, DateTime, String, select
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base
from app.dates import start_of_today_func
from app.wrappers import with_session


class Goods_cost_template(Base):
    __tablename__ = 'goods_cost_templates'

    id: Mapped[int] = mapped_column(primary_key=True)
    seller_id: Mapped[int] = mapped_column(ForeignKey('sellers.id'))
    template_type: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime)

    @classmethod
    @with_session
    async def cost_template_send(cls, session, seller_id, template_type):
        """
        Метод для записи нового шаблона при отправке
        """
        async with session.begin_nested():
            new_template = cls(
                seller_id=seller_id,
                template_type=template_type,
                created_at=datetime.now()
            )
            session.add(new_template)
        await session.commit()
        return new_template

    @classmethod
    @with_session
    async def cost_template_upload(cls, session, seller_id, template_type):
        """
        Метод для записи нового шаблона при загрузке
        """
        async with session.begin_nested():
            new_template = cls(
                seller_id=seller_id,
                template_type=template_type,
                created_at=datetime.now()
            )
            session.add(new_template)
        await session.commit()
        return new_template

    @classmethod
    @with_session
    async def check_cost_template_sent_today(cls, session, seller_id):
        """
        Метод для проверки, отправлялся ли сегодня шаблон
        """
        start_of_today = await start_of_today_func()
        # print(start_of_today)
        template_sent = await session.scalar(select(cls.id).
                             where(cls.seller_id==seller_id,
                                   cls.created_at>start_of_today))
        # print(template_sent)
        if template_sent:
            return True
        else:
            return False