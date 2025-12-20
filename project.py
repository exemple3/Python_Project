import asyncio
import json
import sqlite3
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ConversationHandler
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove
from datetime import date

BOT_TOKEN = '8419712960:AAEQH0LNrebnCKV3eOfWJk8WBIrkdZihxWs'

DATABASE_NAME = 'КБЖУ.db'


reply_keyboard = [
    ['В начало', '🍽 Записать прием'],
    ['📊 Статистика', '📖 История', '⚖️ Ед. измерения'],
    ['🏋️ Активности', '❓ Помощь']]
markup = ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=False, resize_keyboard=True)

GENDER = 0
AGE = 1
HEIGHT = 2
WEIGHT = 3
GOAL = 4
STOPPING = 99

MEAL_NAME = 10
MEAL_QUANTITY = 11


def get_user_data(user_id):
    """
    Извлекает полную информацию о пользователе из таблицы users по его ID
    return: Кортеж с данными из БД или None если пользователь не найден.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    data = cursor.fetchone()
    conn.close()
    return data


def save_user_profile(user_id, profile_data):
    """
    Извлекает полную информацию о пользователе из таблицы users по его ID
    return: Кортеж с данными из БД или None если пользователь не найден
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    fields = 'user_id, gender, age, height, weight, goal, state'
    placeholders = '?, ?, ?, ?, ?, ?, ?'

    values = (
        user_id,
        profile_data['gender'],
        profile_data['age'],
        profile_data['height'],
        profile_data['weight'],
        profile_data['goal'],
        str(STOPPING)
    )

    cursor.execute(f'''
        INSERT OR REPLACE INTO users ({fields}) 
        VALUES ({placeholders})
    ''', values)

    conn.commit()
    conn.close()


def calculate_and_save_kbju(user_id, data):
    """
    Рассчитывает норму калорий по формуле Миффлина-Сан Жеора и БЖУ, затем сохраняет их в БД
    return: Рассчитанная суточная норма калорий
    """
    DEFAULT_ACTIVITY_LEVEL = 1.55

    BMR = (10 * data['weight']) + (6.25 * data['height']) - (5 * data['age'])
    BMR += (5 if data['gender'] == 'муж' else -161)

    TDEE = BMR * DEFAULT_ACTIVITY_LEVEL

    if data['goal'] == 'Похудение':
        daily_kcal = TDEE - 500
    elif data['goal'] == 'Набор веса':
        daily_kcal = TDEE + 300
    else:
        daily_kcal = TDEE

    protein_g = daily_kcal * 0.3 / 4
    fat_g = daily_kcal * 0.2 / 9
    carb_g = daily_kcal * 0.5 / 4

    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        UPDATE users 
        SET daily_kcal = ?, daily_protein = ?, daily_fat = ?, daily_carb = ?, activity_level = ?
        WHERE user_id = ?
    ''', (int(daily_kcal), round(protein_g, 1), round(fat_g, 1), round(carb_g, 1), DEFAULT_ACTIVITY_LEVEL, user_id))

    conn.commit()
    conn.close()

    return int(daily_kcal)


async def start_registration(update, context):
    """
    Начинает процесс регистрации. Если пользователь уже есть в БД — выводит его норму и завершает диалог.
    """
    username = update.message.from_user.first_name
    user_id = update.message.from_user.id

    user_data = get_user_data(user_id)
    if user_data and user_data[2] is not None:
        daily_kcal = user_data[8]
        await update.message.reply_text(
            f"Привет {username}. Твоя дневная норма: {daily_kcal} ккал.\n"
            "Используй /track для записи приемов пищи""\nХочешь что-то узнать - пиши /help"
            "\n\n!Обязательно посмотри перевод единиц измерения - так будет проще вычислить граммовку! /units",
            reply_markup=markup
        )
        return ConversationHandler.END

    context.user_data['profile'] = {}

    gender_keyboard = [['Муж', 'Жен']]
    await update.message.reply_text(
        f"Привет, {username}! Расскажи о себе."
        "\nКакой у тебя пол?",
        reply_markup=ReplyKeyboardMarkup(gender_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

    return GENDER


async def get_age(update, context):
    """
    Принимает пол пользователя и запрашивает возраст
    """
    text = update.message.text

    if text.lower() not in ['муж', 'жен']:
        await update.message.reply_text("Пожалуйста, выбери пол, используя кнопки: 'Муж' или 'Жен'.")
        return GENDER

    context.user_data['profile']['gender'] = text.lower()

    await update.message.reply_text(
        "Сколько тебе лет? (Только число)",
        reply_markup=ReplyKeyboardRemove()
    )
    return AGE


async def get_height(update, context):
    """
    Проверяет корректность возраста и запрашивает рост
    """
    try:
        age = int(update.message.text)
        if not 1 <= age <= 100:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи настоящий возраст (например: 20)")
        return AGE

    context.user_data['profile']['age'] = age

    await update.message.reply_text(
        "Напиши свой рост в сантиметрах (только число)"
    )
    return HEIGHT


async def get_weight(update, context):
    """
    Проверяет корректность роста и запрашивает текущий вес
    """
    try:
        height = float(update.message.text.replace(',', '.'))
        if not 100 <= height <= 250: raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи настоящий рост в сантиметрах (например: 180).")
        return HEIGHT

    context.user_data['profile']['height'] = height

    await update.message.reply_text(
        "Напиши свой текущий вес в килограммах (например, 75.5)"
    )
    return WEIGHT


async def get_goal(update, context):
    """
    Проверяет корректность веса и запрашивает цель (похудение, набор, поддержание)
    """
    try:
        weight = float(update.message.text.replace(',', '.'))
        if not 30 <= weight <= 300: raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, укажи настоящий вес в килограммах (например, 80.2).")
        return WEIGHT

    context.user_data['profile']['weight'] = weight

    goal_keyboard = [
        ['Похудение', 'Поддержание веса'],
        ['Набор веса']
    ]
    await update.message.reply_text(
        "Какая у тебя цель: Похудеть, Поддерживать вес, Набрать?",
        reply_markup=ReplyKeyboardMarkup(goal_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )
    return GOAL


async def end_registration(update, context):
    """
    Завершает регистрацию, сохраняет данные, рассчитывает норму КБЖУ и выводит итог
    """
    user_input = update.message.text
    user_id = update.message.from_user.id

    if user_input not in ['Похудение', 'Поддержание веса', 'Набор веса']:
        await update.message.reply_text("Пожалуйста, выбери цель, используй кнопки.")
        return GOAL

    context.user_data['profile']['goal'] = user_input

    save_user_profile(user_id, context.user_data['profile'])

    daily_kcal = calculate_and_save_kbju(user_id, context.user_data['profile'])

    await update.message.reply_text(
        f"Спасибо за регистрацию!\n\n"
        f"Твоя суточная норма калорий для цели {user_input}: {daily_kcal} ккал.\n"
        "Теперь можешь начать отслеживать приемы пищи, используя команду /track"
        "\n!Обязательно посмотри перевод единиц измерения - так будет проще вычислить граммовку! /units",
        reply_markup=markup
    )
    return ConversationHandler.END


async def cancel(update, context):
    """
    Отменяет любой процесс и возвращает в главное меню
    """
    await update.message.reply_text(
        'Регистрация отменена. Чтобы начать заново, используй /start.',
        reply_markup=markup
    )
    return ConversationHandler.END


async def help_command(update, context):
    """
    Выводит список всех доступных команд бота с их кратким описанием
    """
    await update.message.reply_text('Ты можешь использовать такие команды как: '
                                    '\n /start - для начала '
                                    '\n /track - для записи приёма пищи'
                                    '\n /history - для просмотра истории записей приёмов пищи'
                                    '\n /reset - для удаления последнего приёма пищи'
                                    '\n /status - для просмотра данных на сегодня'
                                    '\n /delete - для полного удаления данных о пользователе'
                                    '\n /units - для просмотра перевода величин измерения'
                                    '\n /activities - для просмотра активностей для сжигания калорий',
                                    reply_markup=markup)


async def echo(update, context):
    await update.message.reply_text(f'Такой комманды нет, используй /help', reply_markup=markup)


def save_daily_log(user_id, meal_text, items_to_log):
    """
    Записывает список распознанных продуктов в таблицу daily_log
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    today_date = date.today().isoformat()

    for item in items_to_log:
        cursor.execute('''
            INSERT INTO daily_log 
            (user_id, date, meal_text, item_name, quantity, unit, kcal, protein, fat, carb) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            today_date,
            meal_text,
            item['name'],
            item['quantity'],
            item['unit'],
            item['kcal'],
            item['protein'],
            item['fat'],
            item['carb']
        ))

    conn.commit()
    conn.close()
    return True


def get_daily_summary(user_id):
    """
    Суммирует потребленные КБЖУ за текущий день
    return: Словарь с суммами калорий, белков, жиров и углеводов
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    today_date = date.today().isoformat()

    cursor.execute(f'''
        SELECT 
            SUM(kcal), SUM(protein), SUM(fat), SUM(carb) 
        FROM daily_log 
        WHERE user_id = ? AND date = ?
    ''', (user_id, today_date))

    summary = cursor.fetchone()

    conn.close()

    if summary and summary[0] is not None:
        return {
            'kcal': int(summary[0]),
            'protein': round(summary[1], 1),
            'fat': round(summary[2], 1),
            'carb': round(summary[3], 1),
        }
    else:
        return {'kcal': 0, 'protein': 0, 'fat': 0, 'carb': 0}


def get_product_kbju(product_name):
    """
    Ищет КБЖУ продукта в БД в таблице 'foods'
    return: Словарь с КБЖУ на 100г или None, если продукт не найден
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT calories, protein, fat, carbs 
        FROM foods 
        WHERE name COLLATE NOCASE = ?
    ''', (product_name.lower(),))

    data = cursor.fetchone()
    conn.close()

    if data:
        return {
            'name': product_name,
            'kcal_100': data[0],
            'protein_100': data[1],
            'fat_100': data[2],
            'carb_100': data[3]
        }
    return None


async def start_tracking(update, context):
    """
    Обрабатывает /track. Проверяет регистрацию и запрашивает название продукта
    """
    user_id = update.message.from_user.id
    user_data = get_user_data(user_id)

    if not user_data or user_data[2] is None:
        await update.message.reply_text("Сначала пройдите регистрацию, используя команду /start.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Что вы съели? Введите точное название продукта (например: Гречка, Куриное филе)."
        "\n\nВозможно нужно указать более точно (например: сметана 20%) или во множественном числе."
        "\n\nИ обязательно посмотри перевод единиц измерения - так будет проще вычислить граммовку: /units",
        reply_markup=ReplyKeyboardRemove()
    )

    return MEAL_NAME


async def get_meal_quantity(update, context):
    """
    Ищет продукт в базе
    Если найден — запрашивает вес, если нет — просит ввести заново
    """
    product_name = update.message.text.strip()

    product_data = get_product_kbju(product_name)

    if product_data is None:
        await update.message.reply_text(
            f"❌ Мы пока не умеем распознавать с ошибками, поэтому продукт {product_name} не найден в базе данных. "
            "Пожалуйста, введи другое название, возможно нужно указать более точно (например: сметана 20%) или отмените /cancel."
        )
        return MEAL_NAME

    context.user_data['temp_log'] = {'product_data': product_data}
    context.user_data['temp_log']['original_text'] = product_name

    await update.message.reply_text(
        f"✅ Продукт {product_data['name']} найден.\n"
        "Теперь введи количество в граммах (только число, например, 150):"
    )

    return MEAL_QUANTITY


from datetime import date


def delete_user_data(user_id):
    """
    Полностью удаляет профиль пользователя и все его записи из БД
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('DELETE FROM daily_log WHERE user_id = ?', (user_id,))

    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))

    conn.commit()
    conn.close()


async def delete_command(update, context):
    """
    Обрабатывает /delete - полностью удаляет данные пользователя
    """
    user_id = update.message.from_user.id
    username = update.message.from_user.first_name

    delete_user_data(user_id)

    await update.message.reply_text(
        f"🗑️ Твой профиль и все данные полностью удалены.\n"
        "Чтобы начать заново, используй команду /start."
    )


def delete_last_log_entry(user_id):
    """
    Удаляет самую последнюю запись о приеме пищи из истории пользователя
    return: Строка с описанием удаленного продукта или None
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('''
        SELECT log_id, item_name, quantity, kcal
        FROM daily_log
        WHERE user_id = ?
        ORDER BY log_id DESC
        LIMIT 1
    ''', (user_id,))

    last_entry = cursor.fetchone()

    if last_entry:
        log_id, item_name, quantity, kcal = last_entry

        cursor.execute('DELETE FROM daily_log WHERE log_id = ?', (log_id,))
        conn.commit()
        conn.close()

        return f"{quantity} г {item_name} ({kcal} ккал)"
    else:
        conn.close()
        return None


async def reset_last_meal(update, context):
    """
    Обрабатывает /reset - удаляет последний прием пищи и показывает новую статистику
    """
    user_id = update.message.from_user.id

    deleted_info = delete_last_log_entry(user_id)

    if deleted_info:
        summary = get_daily_summary(user_id)
        user_data = get_user_data(user_id)
        daily_kcal_norm = user_data[8]

        await update.message.reply_text(
            f"↩️ Удален последний прием пищи: {deleted_info}.\n"
            f"Новый остаток: {daily_kcal_norm - summary['kcal']} ккал."
        )
    else:
        await update.message.reply_text("Нет записей для удаления за сегодня.")


async def status_command(update, context):
    """
    Обрабатывает /status - показывает КБЖУ за день
    """
    user_id = update.message.from_user.id

    user_data = get_user_data(user_id)
    if not user_data or user_data[2] is None:
        await update.message.reply_text("Сначала пройди регистрацию, используя команду /start.")
        return

    summary = get_daily_summary(user_id)

    daily_kcal_norm = user_data[8]
    daily_protein_norm = user_data[9]
    daily_fat_norm = user_data[10]
    daily_carb_norm = user_data[11]

    kcal_remaining = daily_kcal_norm - summary['kcal']
    protein_remaining = round(daily_protein_norm - summary['protein'], 1)
    fat_remaining = round(daily_fat_norm - summary['fat'], 1)
    carb_remaining = round(daily_carb_norm - summary['carb'], 1)

    status_message = (
        f"📅 Твой КБЖУ на {date.today().strftime('%d.%m.%y')}:\n\n"

        f"⚡ КАЛОРИИ\n"
        f"   Съедено: {summary['kcal']} / {daily_kcal_norm} ккал\n"
        f"   Осталось: {kcal_remaining} ккал\n\n"

        f"💪 БЕЛКИ\n"
        f"   Съедено: {summary['protein']} / {daily_protein_norm} г\n"
        f"   Осталось: {protein_remaining} г\n\n"

        f"🥑 ЖИРЫ\n"
        f"   Съедено: {summary['fat']} / {daily_fat_norm} г\n"
        f"   Осталось: {fat_remaining} г\n\n"

        f"🍞 УГЛЕВОДЫ\n"
        f"   Съедено: {summary['carb']} / {daily_carb_norm} г\n"
        f"   Осталось: {carb_remaining} г"
        f"\n\nТы молодец! "
    )

    await update.message.reply_text(status_message, reply_markup=markup)

async def save_and_finish_tracking(update, context):
    """
    Рассчитывает КБЖУ, сохраняет в историю, выводит остаток нормы на день
    и предупреждает при превышении лимита
    """
    user_id = update.message.from_user.id

    try:
        quantity_g = float(update.message.text.replace(',', '.'))
        if quantity_g <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Пожалуйста, введи корректное количество в граммах (число больше 0).")
        return MEAL_QUANTITY

    temp_data = context.user_data['temp_log']
    product = temp_data['product_data']
    original_text = temp_data['original_text']

    ratio = quantity_g / 100.0
    kcal_total = int(product['kcal_100'] * ratio)
    protein_total = round(product['protein_100'] * ratio, 1)
    fat_total = round(product['fat_100'] * ratio, 1)
    carb_total = round(product['carb_100'] * ratio, 1)

    log_item = {
        'name': product['name'],
        'quantity': quantity_g,
        'unit': 'г',
        'kcal': kcal_total,
        'protein': protein_total,
        'fat': fat_total,
        'carb': carb_total
    }
    save_daily_log(user_id, f"{quantity_g} г {original_text}", [log_item])

    summary = get_daily_summary(user_id)
    user_data = get_user_data(user_id)

    daily_kcal_norm = user_data[8]
    total_eaten_kcal = summary['kcal']
    remaining_kcal = daily_kcal_norm - total_eaten_kcal

    daily_protein_norm = user_data[9]
    daily_fat_norm = user_data[10]
    daily_carb_norm = user_data[11]

    overlimit_message = ""
    if remaining_kcal < 0:
        overlimit_message = (
            f"\n\n⚠️ Внимание! Лимит калорий превышен на {abs(remaining_kcal)} ккал."
            f"\nРекомендуем сжечь лишнее. Введи /activities, чтобы выбрать подходящее занятие."
        )

    meal_info = (
        f"✅ Запись добавлена: {quantity_g} г {product['name']}\n"
        f"КБЖУ: {kcal_total} ккал, \nБелки: {protein_total} г\nЖиры: {fat_total} г\nУглеводы: {carb_total} г"
    )

    summary_info = (
        f"📊 Ваш баланс на {date.today().strftime('%d.%m.%y')}:\n"

        f"🔹 ККАЛ: Съедено {summary['kcal']} из {daily_kcal_norm}\n"
        f"⚡ Остаток: {daily_kcal_norm - summary['kcal']} ккал\n\n"

        f"🔹 БЕЛКИ: Съедено {summary['protein']} из {daily_protein_norm} г\n"
        f"🔹 ЖИРЫ: Съедено {summary['fat']} из {daily_fat_norm} г\n"
        f"🔹 УГЛЕВОДЫ: Съедено {summary['carb']} из {daily_carb_norm} г"
        f"\n\n!Хочешь узнать как сжечь калории, жми /activities"
    )

    await update.message.reply_text(
        f"{meal_info}\n\n{summary_info}{overlimit_message}",
        reply_markup=markup
    )

    return ConversationHandler.END


def get_all_activities():
    """
    Получает список всех активностей из таблицы
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT name, calories_per_hour FROM activities')
    data = cursor.fetchall()
    conn.close()
    return data


async def activities_command(update, context):
    """
    Выводит список активностей из БД
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, category, calories_per_hour FROM activities')
    acts = cursor.fetchall()
    conn.close()

    if not acts:
        await update.message.reply_text("В таблице activities пока нет данных.")
        return

    context.user_data['activities_list'] = [a[0] for a in acts]

    message = "🏋️ Активности, которые помогут сжечь калории:\n\n"
    for i, (act_id, name, category, energy) in enumerate(acts, 1):
        message += f"{i}. {name} — {energy} ккал/ч\n"

    message += "\nНапиши номер активности, если хочешь узнать подробное описание."

    await update.message.reply_text(message, reply_markup=markup)


async def handle_message(update, context):
    """
    Обрабатывает текстовые сообщения
    Если введено число — ищет описание активности по индексу
    """
    text = update.message.text.strip()
    user_id = update.message.from_user.id

    if text.isdigit() and 'activities_list' in context.user_data:
        index = int(text) - 1
        ids_list = context.user_data['activities_list']

        if 0 <= index < len(ids_list):
            activity_id = ids_list[index]

            conn = sqlite3.connect(DATABASE_NAME)
            cursor = conn.cursor()
            cursor.execute('SELECT name, description FROM activities WHERE id = ?', (activity_id,))
            res = cursor.fetchone()
            conn.close()

            if res:
                name, description = res
                desc_text = description if description else "Описание для этой активности пока не добавлено."
                await update.message.reply_text(
                    f"<b>{name}</b>\n\n{desc_text}",
                    parse_mode='HTML')
                return
        else:
            await update.message.reply_text("Активности с таким номером нет в списке.")
            return

def get_all_units():
    """
    Получает список всех единиц измерения и их коэффициентов из БД
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT unit, conversion_factor FROM unit_conversion')
    data = cursor.fetchall()
    conn.close()
    return data


async def units_command(update, context):
    """
    Обрабатывает /units - показывает единицы измерения
    """
    units_data = get_all_units()

    if not units_data:
        await update.message.reply_text(
            "Единиц измерения нет.",
            reply_markup=markup
        )
        return

    message = "⚖️ Единицы измерения (перевод в граммы):\n\n"
    for unit, factor in units_data:
        display_factor = int(factor) if factor == int(factor) else factor
        message += f"• {unit.capitalize()}: {display_factor} г\n"

    await update.message.reply_text(message, reply_markup=markup)


def get_user_history(user_id, limit=15):
    """
    Получает последние записи о питании пользователя
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT date, item_name, quantity, unit, kcal 
        FROM daily_log 
        WHERE user_id = ? 
        ORDER BY log_id DESC 
        LIMIT ?
    ''', (user_id, limit))
    data = cursor.fetchall()
    conn.close()
    return data


async def history_command(update, context):
    """
    Выводит историю приемов пищи
    """
    user_id = update.message.from_user.id
    history = get_user_history(user_id)

    if not history:
        await update.message.reply_text("История приемов пищи пуста. Начни с команды /track.")
        return

    message = "📖 История (последние записи):\n\n"

    current_date = ""
    for meal_date, name, weight, unit, kcal in history:
        if meal_date != current_date:
            display_date = ".".join(meal_date.split('-')[::-1][:2])
            message += f"📅 {display_date}\n"
            current_date = meal_date

        message += f"• {name}: {int(weight)} {unit} — <b>{kcal} ккал</b>\n"

    await update.message.reply_text(message, reply_markup=markup, parse_mode='HTML')


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    reg_handler = ConversationHandler(
        entry_points=[
            CommandHandler('start', start_registration),
            MessageHandler(filters.Text('В начало'), start_registration)  # Добавили кнопку
        ],
        states={
            GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_age)],
            AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_height)],
            HEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weight)],
            WEIGHT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_goal)],
            GOAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, end_registration)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    track_handler = ConversationHandler(
        entry_points=[
            CommandHandler('track', start_tracking),
            MessageHandler(filters.Text('🍽 Записать прием'), start_tracking)  # Добавили кнопку
        ],
        states={
            MEAL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_meal_quantity)],
            MEAL_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_and_finish_tracking)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        allow_reentry=True
    )

    application.add_handler(reg_handler)
    application.add_handler(track_handler)

    application.add_handler(MessageHandler(filters.Text('📊 Статистика'), status_command))
    application.add_handler(MessageHandler(filters.Text('📖 История'), history_command))
    application.add_handler(MessageHandler(filters.Text('⚖️ Ед. измерения'), units_command))
    application.add_handler(MessageHandler(filters.Text('🏋️ Активности'), activities_command))
    application.add_handler(MessageHandler(filters.Text('❓ Помощь'), help_command))

    application.add_handler(CommandHandler('history', history_command))
    application.add_handler(CommandHandler('activities', activities_command))
    application.add_handler(CommandHandler('units', units_command))
    application.add_handler(CommandHandler('reset', reset_last_meal))
    application.add_handler(CommandHandler('delete', delete_command))
    application.add_handler(CommandHandler('status', status_command))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    application.run_polling()

if __name__ == '__main__':
    main()