from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from config import Config


class Keyboards:
    """
    Класс-фабрика для создания клавиатур бота.

    Предоставляет статические методы для генерации различных типов клавиатур:
    - Reply-клавиатуры (главное меню)
    - Inline-клавиатуры (выбор криптовалют, действия, уведомления)

    Все методы возвращают готовые объекты клавиатур для использования в ответах.
    """

    @staticmethod
    def get_main_menu():
        """
        Создает главное меню с reply-кнопками.

        Возвращает клавиатуру с основными разделами:
        - Котировки
        - Популярные
        - Мои уведомления
        - Статистика
        - Помощь

        Returns:
            ReplyKeyboardMarkup: Клавиатура главного меню
        """
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="💰 Котировки"),
                    KeyboardButton(text="🚀 Популярные")
                ],
                [
                    KeyboardButton(text="🔔 Мои уведомления"),
                    KeyboardButton(text="📊 Статистика")
                ],
                [
                    KeyboardButton(text="📋 Помощь")
                ]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие👇"
        )
        return keyboard

    @staticmethod
    def get_crypto_selection():
        """
        Создает inline-клавиатуру для выбора криптовалюты.

        Формирует кнопки на основе POPULAR_CRYPTO из конфига,
        располагая их по 3 в ряд. Добавляет кнопки управления:
        - Все котировки
        - Новое уведомление
        - Главное меню

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопками криптовалют и управления
        """
        buttons = []
        row = []

        for crypto_name, crypto_pair in Config.POPULAR_CRYPTO.items():
            row.append(InlineKeyboardButton(
                text=crypto_name,
                callback_data=f"crypto_{crypto_pair}"
            ))

            if len(row) == 3:
                buttons.append(row)
                row = []

        if row:
            buttons.append(row)

        # Кнопки управления
        buttons.append([
            InlineKeyboardButton(text="📈 Все котировки", callback_data="all_prices"),
            InlineKeyboardButton(text="➕ Новое уведомление", callback_data="new_alert_from_select")
        ])

        buttons.append([
            InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def get_price_actions(symbol: str):
        """
        Создает клавиатуру действий для выбранной криптовалюты.

        Args:
            symbol (str): Торговый символ

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопками:
                - Подробная информация
                - Установка уведомления
                - Назад к списку
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Подробно", callback_data=f"detail_{symbol}"),
                InlineKeyboardButton(text="🔔 Уведомить", callback_data=f"alert_{symbol}")
            ],
            [
                InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_crypto")
            ]
        ])

    @staticmethod
    def get_alert_setup(symbol: str):
        """
        Создает клавиатуру для настройки уведомления по криптовалюте.

        Args:
            symbol (str): Торговый символ

        Returns:
            InlineKeyboardMarkup: Клавиатура с вариантами уведомлений
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Выше на 5%", callback_data=f"alert_up_percent_{symbol}_5"),
                InlineKeyboardButton(text="📉 Ниже на 5%", callback_data=f"alert_down_percent_{symbol}_5")
            ],
            [
                InlineKeyboardButton(text="📈 Выше на 10%", callback_data=f"alert_up_percent_{symbol}_10"),
                InlineKeyboardButton(text="📉 Ниже на 10%", callback_data=f"alert_down_percent_{symbol}_10")
            ],
            [
                InlineKeyboardButton(text="⚙️ Своя цена", callback_data=f"alert_custom_{symbol}"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="alert_help")
            ],
            [
                InlineKeyboardButton(text="↩️ Назад", callback_data=f"back_to_price_{symbol}")
            ]
        ])

    @staticmethod
    def get_alerts_menu():
        """
        Создает меню управления уведомлениями.

        Returns:
            InlineKeyboardMarkup: Клавиатура с действиями над уведомлениями
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Новое уведомление", callback_data="new_alert"),
                InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_alerts")
            ],
            [
                InlineKeyboardButton(text="📋 Список уведомлений", callback_data="list_alerts"),
                InlineKeyboardButton(text="❓ Помощь", callback_data="alert_help")
            ],
            [
                InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")
            ]
        ])

    @staticmethod
    def get_alert_management(alert_id: int, symbol: str):
        """
        Создает клавиатуру для управления конкретным уведомлением.

        Args:
            alert_id (int): Идентификатор уведомления
            symbol (str): Торговый символ

        Returns:
            InlineKeyboardMarkup: Клавиатура с кнопками управления
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_alert_{alert_id}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_alert_{alert_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_alerts_list")
            ]
        ])

    @staticmethod
    def get_back_button(callback_data: str = "back_to_main"):
        """
        Создает простую клавиатуру с одной кнопкой "Назад".

        Args:
            callback_data (str): Данные для callback при нажатии кнопки

        Returns:
            InlineKeyboardMarkup: Клавиатура с одной кнопкой возврата
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data=callback_data)]
        ])

    @staticmethod
    def get_yes_no_keyboard(yes_callback: str, no_callback: str):
        """
        Создает клавиатуру для подтверждения действия (Да/Нет).

        Args:
            yes_callback (str): Callback data для кнопки "Да"
            no_callback (str): Callback data для кнопки "Нет"

        Returns:
            InlineKeyboardMarkup: Клавиатура с двумя кнопками подтверждения
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=yes_callback),
                InlineKeyboardButton(text="❌ Нет", callback_data=no_callback)
            ]
        ])

    @staticmethod
    def get_cancel_keyboard(callback_data: str = "cancel_alert"):
        """
        Создает клавиатуру для отмены текущего действия.

        Args:
            callback_data (str): Данные для callback при нажатии кнопки отмены

        Returns:
            InlineKeyboardMarkup: Клавиатура с одной кнопкой отмены
        """
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)]
        ])