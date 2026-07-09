from app.wrappers import log_and_notify_admin


class SubscriptionTypes():
    items = []

    def __init__(self, subscription_type, duration, subscription_name, price):
        self.subscription_type = subscription_type
        self.duration = duration
        self.subscription_name = subscription_name
        self.price = price
        SubscriptionTypes.items.append(self)

    @classmethod
    def __getitem__(cls, index):
        return cls.items[index]

trial = SubscriptionTypes("trial", 0, '7 дней',0)
promo = SubscriptionTypes("promo", 0, 'Промо',0)
one_month = SubscriptionTypes("one_month", 1, 'Один месяц',590)
three_month = SubscriptionTypes("three_months",3,'Три месяца', 1620)
six_month = SubscriptionTypes("six_months",6,'Шесть месяцев', 2940)

@log_and_notify_admin
async def get_subscription_name_by_subscription_type(subscription_type):
    for item in SubscriptionTypes.items:
        if item.subscription_type==subscription_type:
            return item.subscription_name

async def get_subscription_price_by_subscription_type(subscription_type):
    for item in SubscriptionTypes.items:
        if item.subscription_type == subscription_type:
            return item.price
    # print(item.subscription_type)
    # print(item.subscription_name)
    # print(item.price)


