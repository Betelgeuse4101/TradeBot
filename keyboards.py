from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from config import Config


class Keyboards:
    """Класс для создания клавиатур"""

    @staticmethod
    def get_main_menu():
        """Главное меню"""
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
                    KeyboardButton(text="⚙️ Настройки"),
                    KeyboardButton(text="📋 Помощь")
                ]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие👇"
        )
        return keyboard

    @staticmethod
    def get_crypto_selection():
        """Выбор криптовалюты"""
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
        """Действия с выбранной криптой"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Подробно", callback_data=f"detail_{symbol}"),
                InlineKeyboardButton(text="🔔 Уведомить", callback_data=f"alert_{symbol}")
            ],
            [
                InlineKeyboardButton(text="📈 График", callback_data=f"chart_{symbol}"),
                InlineKeyboardButton(text="💾 Избранное", callback_data=f"fav_{symbol}")
            ],
            [
                InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_crypto")
            ]
        ])

    @staticmethod
    def get_alert_setup(symbol: str):
        """Настройка уведомления"""
        # Получаем текущую цену для предложений
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
                InlineKeyboardButton(text="❓ Помощь", callback_data=f"alert_help_{symbol}")
            ],
            [
                InlineKeyboardButton(text="↩️ Назад", callback_data=f"back_to_price_{symbol}")
            ]
        ])

    @staticmethod
    def get_alerts_menu():
        """Меню уведомлений"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Новое уведомление", callback_data="new_alert"),
                InlineKeyboardButton(text="🗑️ Очистить все", callback_data="clear_alerts")
            ],
            [
                InlineKeyboardButton(text="📋 Список уведомлений", callback_data="list_alerts"),
                InlineKeyboardButton(text="⚙️ Настройки", callback_data="alert_settings")
            ],
            [
                InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")
            ]
        ])

    @staticmethod
    def get_alert_management(alert_id: int, symbol: str):
        """Управление конкретным уведомлением"""
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
    def get_settings_menu():
        """Меню настроек"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⏰ Интервал уведомлений", callback_data="interval_setting"),
                InlineKeyboardButton(text="🎨 Тема", callback_data="theme_setting")
            ],
            [
                InlineKeyboardButton(text="🔕 Уведомления", callback_data="notify_setting"),
                InlineKeyboardButton(text="💾 Экспорт данных", callback_data="export_data")
            ],
            [
                InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")
            ]
        ])

    @staticmethod
    def get_back_button(callback_data: str = "back_to_main"):
        """Кнопка Назад"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data=callback_data)]
        ])

    @staticmethod
    def get_yes_no_keyboard(yes_callback: str, no_callback: str):
        """Клавиатура Да/Нет"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=yes_callback),
                InlineKeyboardButton(text="❌ Нет", callback_data=no_callback)
            ]
        ])

    @staticmethod
    def get_cancel_keyboard(callback_data: str = "cancel_alert"):
        """Кнопка Отмена"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)]
        ])