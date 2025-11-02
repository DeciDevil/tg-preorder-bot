import os
import logging
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
from sqlalchemy import create_engine, Column, Integer, String, Float, Text, ForeignKey, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import uuid

# ===== НАСТРОЙКИ =====
BOT_TOKEN = "8223614262:AAGnc1-H09YroqTyALJTzabFW5RHlvnPcEc"
ADMIN_CHAT_ID = "Xcelestiall"

# ===== БАЗА ДАННЫХ =====
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False)
    full_name = Column(String)
    phone_number = Column(String)
    created_at = Column(DateTime, default=datetime.now)

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False)
    photo_url = Column(String)
    sizes = Column(String)
    preorder_days = Column(Integer)
    expected_date = Column(String)
    preorder_note = Column(Text)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    size = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    payment_status = Column(String, default='pending')
    yookassa_payment_id = Column(String)
    customer_name = Column(String)
    customer_phone = Column(String)
    customer_address = Column(String)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User")
    product = relationship("Product")

engine = create_engine('sqlite:///shop.db')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# ===== ТЕСТОВЫЕ ПЛАТЕЖИ =====
test_payments = {}

def create_payment(amount, description, order_id):
    payment_id = f"test_{order_id}_{uuid.uuid4().hex[:8]}"
    test_payments[payment_id] = {"status": "pending", "amount": amount, "order_id": order_id}
    
    class MockPayment:
        def __init__(self, pid):
            self.id = pid
    return MockPayment(payment_id)

def confirm_test_payment(payment_id):
    if payment_id in test_payments:
        test_payments[payment_id]["status"] = "succeeded"
        return True
    return False

# ===== КЛАВИАТУРЫ =====
def main_menu():
    keyboard = [['🚀 Каталог предзаказов'], ['📞 Поддержка', '📋 Мои предзаказы']]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

def sizes_keyboard(sizes_list):
    keyboard = []
    row = []
    for size in sizes_list:
        row.append(InlineKeyboardButton(size, callback_data=f"size_{size}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

def payment_keyboard(payment_id):
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить предзаказ", callback_data=f"pay_{payment_id}")],
        [InlineKeyboardButton("📋 Мои предзаказы", callback_data="my_orders")]
    ]
    return InlineKeyboardMarkup(keyboard)

# ===== ОСНОВНОЙ КОД БОТА =====
logging.basicConfig(level=logging.INFO)
TAKING_NAME, TAKING_PHONE, TAKING_ADDRESS = range(3)
user_temp_data = {}

def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    db_user = session.query(User).filter_by(telegram_id=user.id).first()
    if not db_user:
        db_user = User(telegram_id=user.id, full_name=user.full_name)
        session.add(db_user)
        session.commit()

    update.message.reply_text(
        f"👋 Привет, {user.first_name}!\n"
        "Добро пожаловать в магазин стилизованной одежды! 🎮\n\n"
        "У нас только эксклюзивные предзаказы!\n\n"
        "Выберите действие:",
        reply_markup=main_menu()
    )

def show_catalog(update: Update, context: CallbackContext) -> None:
    products = session.query(Product).all()
    if not products:
        update.message.reply_text("📭 Каталог предзаказов пока пуст. Скоро появятся новые эксклюзивы!")
        return

    update.message.reply_text("🚀 Каталог предзаказов:\nВыберите понравившийся товар:")
    
    for product in products:
        caption = (
            f"🚀 ПРЕДЗАКАЗ\n"
            f"{product.name}\n\n"
            f"{product.description}\n\n"
            f"⏰ Срок предзаказа: {product.preorder_days} дней\n"
            f"📅 Ожидаемая дата: {product.expected_date}\n"
            f"💡 {product.preorder_note}\n\n"
            f"💵 Цена: {product.price} руб."
        )
        
        keyboard = [[InlineKeyboardButton("🚀 Забронировать", callback_data=f"product_{product.id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        if product.photo_url:
            update.message.reply_photo(photo=product.photo_url, caption=caption, reply_markup=reply_markup)
        else:
            update.message.reply_text(caption, reply_markup=reply_markup)

def support_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_text(
        "📞 Служба поддержки по предзаказам\n\n"
        "По всем вопросам о предзаказах обращайтесь:\n"
        "• 💬 @ваш_менеджер\n"
        "• 📧 email@example.com\n"
        "• ⏰ Время работы: 10:00-20:00\n\n"
        "Мы всегда рады помочь!"
    )

def button_click(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    data = query.data

    if data.startswith('product_'):
        product_id = int(data.split('_')[1])
        product = session.query(Product).get(product_id)
        if product:
            user_temp_data[query.from_user.id] = {'product_id': product_id}
            sizes = [s.strip() for s in product.sizes.split(',')]
            reply_markup = sizes_keyboard(sizes)
            
            if hasattr(query.message, 'caption'):
                query.edit_message_caption(caption=query.message.caption + f"\n\nВыберите размер:", reply_markup=reply_markup)
            else:
                query.edit_message_text(query.message.text + f"\n\nВыберите размер:", reply_markup=reply_markup)
        return

    if data.startswith('size_'):
        selected_size = data.split('_')[1]
        user_id = query.from_user.id
        user_temp_data[user_id]['size'] = selected_size

        if hasattr(query.message, 'caption'):
            query.edit_message_caption(caption=query.message.caption + f"\n\nВыбран размер: {selected_size}\n\nТеперь введите ваше ФИО для доставки:")
        else:
            query.edit_message_text(query.message.text + f"\n\nВыбран размер: {selected_size}\n\nТеперь введите ваше ФИО для доставки:")
        return TAKING_NAME

    if data.startswith('pay_'):
        payment_id = data.split('_')[1]
        user_id = query.from_user.id
        
        success = confirm_test_payment(payment_id)
        if success:
            order = session.query(Order).filter_by(yookassa_payment_id=payment_id).first()
            if order:
                order.payment_status = 'paid'
                session.commit()
                
                product = session.query(Product).get(order.product_id)
                
                query.edit_message_text(
                    "✅ Предзаказ оплачен!\n\n"
                    "🚀 Ваш предзаказ подтвержден и оплачен!\n\n"
                    f"📦 Заказ №: {order.id}\n"
                    f"👕 Товар: {product.name}\n"
                    f"📏 Размер: {order.size}\n"
                    f"📅 Ожидаемая дата: {product.expected_date}\n\n"
                    "Мы уведомим вас о готовности заказа.\n"
                    "Спасибо за доверие! ❤️"
                )
                
                # Уведомляем админа
                admin_text = (
                    f"🎉 ОПЛАЧЕН ПРЕДЗАКАЗ!\n\n"
                    f"📦 Заказ №: {order.id}\n"
                    f"🎮 Товар: {product.name}\n"
                    f"📏 Размер: {order.size}\n"
                    f"💵 Сумма: {order.amount} руб.\n"
                    f"👤 Клиент: {order.customer_name}\n"
                    f"📞 Телефон: {order.customer_phone}\n"
                    f"🏪 ПВЗ: {order.customer_address}\n"
                    f"📅 Дата поставки: {product.expected_date}\n"
                    f"🆔 TG ID: {user_id}"
                )
                context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)
            else:
                query.edit_message_text("❌ Заказ не найден.")
        else:
            query.edit_message_text("❌ Ошибка при подтверждении платежа.")
        return

    if data == 'my_orders':
        user_id = query.from_user.id
        user_db = session.query(User).filter_by(telegram_id=user_id).first()
        
        if user_db:
            orders = session.query(Order).filter_by(user_id=user_db.id).order_by(Order.id.desc()).limit(3).all()
            if orders:
                text = "📋 Ваши последние предзаказы:\n\n"
                for order in orders:
                    product = session.query(Product).get(order.product_id)
                    status_emoji = "✅" if order.payment_status == 'paid' else "⏳"
                    status_text = "Оплачен" if order.payment_status == 'paid' else "Ожидает оплаты"
                    
                    text += (
                        f"🚀 Предзаказ №{order.id}\n"
                        f"🎮 Товар: {product.name}\n"
                        f"📏 Размер: {order.size}\n"
                        f"💵 Сумма: {order.amount} руб.\n"
                        f"📅 Дата поставки: {product.expected_date}\n"
                        f"📊 Статус: {status_emoji} {status_text}\n"
                        f"────────────────────\n"
                    )
            else:
                text = "📭 У вас еще нет предзаказов."
        else:
            text = "❌ Пользователь не найден."
        
        query.edit_message_text(text)
        return

    query.answer()

def take_name(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    user_temp_data[user_id]['customer_name'] = update.message.text
    update.message.reply_text("📞 Введите ваш номер телефона:\n\nПример: +79123456789 или 89123456789")
    return TAKING_PHONE

def take_phone(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    user_temp_data[user_id]['customer_phone'] = update.message.text
    update.message.reply_text("🏪 Введите адрес ближайшего ПВЗ СДЭК:\n\nПример: Москва, ул. Ленина, д. 1, ПВЗ №123")
    return TAKING_ADDRESS

def take_address(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    user_data = user_temp_data.get(user_id)
    if not user_data:
        update.message.reply_text("❌ Что-то пошло не так. Начните заново через /start")
        return ConversationHandler.END

    user_data['customer_address'] = update.message.text

    product = session.query(Product).get(user_data['product_id'])
    amount = product.price

    user_db = session.query(User).filter_by(telegram_id=user_id).first()
    new_order = Order(
        user_id=user_db.id,
        product_id=product.id,
        size=user_data['size'],
        amount=amount,
        customer_name=user_data['customer_name'],
        customer_phone=user_data['customer_phone'],
        customer_address=user_data['customer_address']
    )
    session.add(new_order)
    session.commit()

    payment = create_payment(amount=amount, description=f"Оплата предзаказа №{new_order.id} - {product.name}", order_id=new_order.id)
    new_order.yookassa_payment_id = payment.id
    session.commit()

    update.message.reply_text(
        f"🚀 Предзаказ оформлен!\n\n"
        f"Вы забронировали товар из предстоящей партии.\n\n"
        f"📦 Заказ №: {new_order.id}\n"
        f"👕 Товар: {product.name}\n"
        f"📏 Размер: {user_data['size']}\n"
        f"💵 Сумма: {amount} руб.\n"
        f"📅 Ожидаемая дата: {product.expected_date}\n"
        f"👤 ФИО: {user_data['customer_name']}\n"
        f"📞 Телефон: {user_data['customer_phone']}\n"
        f"🏪 ПВЗ: {user_data['customer_address']}\n\n"
        f"Для завершения бронирования нажмите кнопку ниже:",
        reply_markup=payment_keyboard(payment.id)
    )

    admin_text = (
        f"🚀 НОВЫЙ ПРЕДЗАКАЗ!\n\n"
        f"📦 Заказ №: {new_order.id}\n"
        f"🎮 Товар: {product.name}\n"
        f"📏 Размер: {user_data['size']}\n"
        f"💵 Сумма: {amount} руб.\n"
        f"👤 Клиент: {user_data['customer_name']}\n"
        f"📞 Телефон: {user_data['customer_phone']}\n"
        f"🏪 ПВЗ: {user_data['customer_address']}\n"
        f"📅 Дата поставки: {product.expected_date}\n"
        f"🆔 TG ID: {user_id}"
    )
    context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=admin_text)

    del user_temp_data[user_id]
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('❌ Оформление предзаказа отменено.', reply_markup=main_menu())
    user_id = update.message.from_user.id
    if user_id in user_temp_data:
        del user_temp_data[user_id]
    return ConversationHandler.END

def my_orders_command(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    user_db = session.query(User).filter_by(telegram_id=user_id).first()
    
    if not user_db:
        update.message.reply_text("❌ Предзаказов не найдено.")
        return

    orders = session.query(Order).filter_by(user_id=user_db.id).order_by(Order.id.desc()).all()
    
    if not orders:
        update.message.reply_text("📭 У вас еще нет предзаказов.\n\nПерейдите в Каталог предзаказов чтобы выбрать товар! 🚀")
        return

    update.message.reply_text("📋 Ваши предзаказы:")
    
    for order in orders[:5]:
        product = session.query(Product).get(order.product_id)
        status_emoji = "✅" if order.payment_status == 'paid' else "⏳"
        status_text = "Оплачен" if order.payment_status == 'paid' else "Ожидает оплаты"
        
        order_text = (
            f"🚀 Предзаказ №{order.id}\n"
            f"🎮 Товар: {product.name}\n"
            f"📏 Размер: {order.size}\n"
            f"💵 Сумма: {order.amount} руб.\n"
            f"📅 Дата поставки: {product.expected_date}\n"
            f"📊 Статус: {status_emoji} {status_text}\n"
            f"📅 Создан: {order.created_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"────────────────────"
        )
        update.message.reply_text(order_text)

def main():
    # Добавляем тестовые товары если их нет
    if session.query(Product).count() == 0:
        products = [
            Product(
                name="Футболка 'Киберпанк 2077'", 
                description="Стильная футболка с дизайном из вселенной Киберпанк 2077. 100% хлопок.", 
                price=1899.99, 
                photo_url="https://via.placeholder.com/400x400/FF6B6B/FFFFFF?text=Cyberpunk+T-Shirt",
                sizes="S,M,L,XL,XXL", 
                preorder_days=14, 
                expected_date="25.12.2023",
                preorder_note="Доставка предзаказов начнется с 25 декабря"
            ),
            Product(
                name="Худи 'The Witcher'", 
                description="Теплое худи с символикой Ведьмака. ЭКСКЛЮЗИВНЫЙ ДИЗАЙН!", 
                price=3499.99, 
                photo_url="https://via.placeholder.com/400x400/4ECDC4/FFFFFF?text=Witcher+Hoodie",
                sizes="M,L,XL,XXL", 
                preorder_days=21, 
                expected_date="15.01.2024",
                preorder_note="Ограниченный тираж - всего 50 штук!"
            )
        ]
        for product in products:
            session.add(product)
        session.commit()
        print("Добавлены тестовые товары")

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.regex('^(🚀 Каталог предзаказов)$'), show_catalog))
    dispatcher.add_handler(MessageHandler(Filters.regex('^(📞 Поддержка)$'), support_command))
    dispatcher.add_handler(MessageHandler(Filters.regex('^(📋 Мои предзаказы)$'), my_orders_command))

    dispatcher.add_handler(CallbackQueryHandler(button_click))

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button_click, pattern='^size_')],
        states={
            TAKING_NAME: [MessageHandler(Filters.text & ~Filters.command, take_name)],
            TAKING_PHONE: [MessageHandler(Filters.text & ~Filters.command, take_phone)],
            TAKING_ADDRESS: [MessageHandler(Filters.text & ~Filters.command, take_address)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    dispatcher.add_handler(conv_handler)

    print("🤖 Бот для предзаказов запущен!")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
