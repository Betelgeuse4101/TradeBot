from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton
)
from typing import List, Dict, Any


class Keyboards:
    """Класс-фабрика для создания клавиатур"""

    @staticmethod
    def get_main_menu():
        """Главное меню"""
        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="📊 Мои портфели")],
                [KeyboardButton(text="➕ Создать портфель")],
                [KeyboardButton(text="🔔 Мои уведомления")],
                [KeyboardButton(text="📈 Популярные активы")],
                [KeyboardButton(text="📋 Помощь")]
            ],
            resize_keyboard=True,
            input_field_placeholder="Выберите действие👇"
        )
        return keyboard

    @staticmethod
    def get_portfolio_empty():
        """Пустой список портфелей"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать портфель", callback_data="create_portfolio")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")]
        ])

    @staticmethod
    def get_portfolio_list(portfolios: List[Dict]):
        """Список портфелей"""
        buttons = []

        for p in portfolios:
            value_str = f"{float(p['total_value']):,.2f} {p['currency']}" if p['total_value'] else "0 RUB"

            buttons.append([
                InlineKeyboardButton(
                    text=f"📁 {p['name']} - {value_str} ({p['assets_count']} активов)",
                    callback_data=f"portfolio_{p['id']}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(text="➕ Новый портфель", callback_data="create_portfolio"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def get_portfolio_actions(portfolio_id: int):
        """Действия с портфелем"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Добавить актив", callback_data=f"add_asset_{portfolio_id}"),
                InlineKeyboardButton(text="📋 Список активов", callback_data=f"list_assets_{portfolio_id}")
            ],
            [
                InlineKeyboardButton(text="🔔 Уведомление", callback_data=f"alert_portfolio_{portfolio_id}"),
                InlineKeyboardButton(text="📊 Статистика", callback_data=f"stats_{portfolio_id}")
            ],
            [
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_portfolio_{portfolio_id}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_portfolio_{portfolio_id}")
            ],
            [InlineKeyboardButton(text="↩️ К списку", callback_data="back_to_portfolios")]
        ])

    @staticmethod
    def get_asset_types():
        """Типы активов"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 Акция", callback_data="asset_type_stock")],
            [InlineKeyboardButton(text="📊 Облигация", callback_data="asset_type_bond")],
            [InlineKeyboardButton(text="📦 ETF", callback_data="asset_type_etf")],
            [InlineKeyboardButton(text="💵 Валюта", callback_data="asset_type_currency")],
            [InlineKeyboardButton(text="📉 Фьючерс", callback_data="asset_type_futures")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])

    @staticmethod
    def get_currencies():
        """Валюты"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🇷🇺 RUB", callback_data="currency_RUB")],
            [InlineKeyboardButton(text="🇺🇸 USD", callback_data="currency_USD")],
            [InlineKeyboardButton(text="🇪🇺 EUR", callback_data="currency_EUR")],
            [InlineKeyboardButton(text="🇨🇳 CNY", callback_data="currency_CNY")],
            [InlineKeyboardButton(text="🇰🇿 KZT", callback_data="currency_KZT")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])

    @staticmethod
    def get_assets_list(assets: List[Dict], portfolio_id: int):
        """Список активов портфеля"""
        buttons = []

        for asset in assets[:10]:
            profit_icon = "🟢" if asset.get('profit', 0) >= 0 else "🔴"
            profit_str = f"{profit_icon} {float(asset.get('profit_percent', 0)):+.2f}%"

            buttons.append([
                InlineKeyboardButton(
                    text=f"{asset['symbol']} - {asset['name'][:20]} {profit_str}",
                    callback_data=f"view_asset_{asset['id']}"
                )
            ])

        if len(assets) > 10:
            buttons.append(
                [InlineKeyboardButton(text="📄 Показать еще", callback_data=f"more_assets_{portfolio_id}_10")])

        buttons.append([InlineKeyboardButton(text="↩️ Назад", callback_data=f"portfolio_{portfolio_id}")])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def get_asset_actions(asset_id: int, portfolio_id: int):
        """Действия с активом"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔔 Уведомление", callback_data=f"alert_asset_{asset_id}"),
                InlineKeyboardButton(text="✏️ Изменить", callback_data=f"edit_asset_{asset_id}")
            ],
            [
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_asset_{asset_id}"),
                InlineKeyboardButton(text="🔄 Обновить цену", callback_data=f"refresh_asset_{asset_id}")
            ],
            [InlineKeyboardButton(text="↩️ К портфелю", callback_data=f"portfolio_{portfolio_id}")]
        ])

    @staticmethod
    def get_asset_search(portfolio_id: int):
        """Клавиатура для поиска активов"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Поиск по названию", callback_data=f"search_asset_{portfolio_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"portfolio_{portfolio_id}")]
        ])

    @staticmethod
    def get_alert_type_selection(target_type: str, target_id: int):
        """Выбор типа уведомления"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📈 Выше цены", callback_data=f"alert_type_price_up_{target_id}"),
                InlineKeyboardButton(text="📉 Ниже цены", callback_data=f"alert_type_price_down_{target_id}")
            ],
            [
                InlineKeyboardButton(text="📈 Выше на %", callback_data=f"alert_type_percent_up_{target_id}"),
                InlineKeyboardButton(text="📉 Ниже на %", callback_data=f"alert_type_percent_down_{target_id}")
            ],
            [InlineKeyboardButton(text="↩️ Назад", callback_data=f"back_to_{target_type}_{target_id}")]
        ])

    @staticmethod
    def get_alerts_list(alerts: List[Dict]):
        """Список уведомлений"""
        buttons = []

        for alert in alerts[:10]:
            if alert['alert_type'] == 'portfolio':
                name = alert.get('portfolio_name', 'Портфель')
                if alert['condition_type'] == 'price':
                    target_display = f"{float(alert['target_value']):,.2f} {alert.get('currency', 'RUB')}"
                else:
                    target_display = f"{float(alert['target_value']):+.1f}%"

                direction = "↑" if alert['direction'] == 'up' else "↓"

                if alert['is_triggered']:
                    status = "✅"
                elif alert['is_active']:
                    status = "⏳"
                else:
                    status = "⏸️"

                text = f"{status} {direction} {name}: {target_display}"
            else:
                asset_name = alert.get('asset_symbol', 'Актив')
                if alert['condition_type'] == 'price':
                    target_display = f"{float(alert['target_value']):,.2f} {alert.get('currency', 'RUB')}"
                else:
                    target_display = f"{float(alert['target_value']):+.1f}%"

                direction = "↑" if alert['direction'] == 'up' else "↓"

                if alert['is_triggered']:
                    status = "✅"
                elif alert['is_active']:
                    status = "⏳"
                else:
                    status = "⏸️"

                text = f"{status} {direction} {asset_name}: {target_display}"

            buttons.append([
                InlineKeyboardButton(
                    text=text,
                    callback_data=f"view_alert_{alert['id']}"
                )
            ])

        buttons.append([
            InlineKeyboardButton(text="➕ Новое уведомление", callback_data="new_alert"),
            InlineKeyboardButton(text="↩️ Назад", callback_data="back_to_main")
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def get_alerts_empty():
        """Пустой список уведомлений"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать уведомление", callback_data="new_alert")],
            [InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")]
        ])

    @staticmethod
    def get_alert_actions(alert_id: int, is_active: bool = True, is_triggered: bool = False):
        """Действия с уведомлением"""
        buttons = []

        buttons.append([
            InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_alert_{alert_id}"),
        ])

        if not is_active or is_triggered:
            buttons.append([
                InlineKeyboardButton(text="🔄 Активировать", callback_data=f"reactivate_alert_{alert_id}")
            ])

        buttons.append([
            InlineKeyboardButton(text="↩️ К списку", callback_data="back_to_alerts")
        ])

        return InlineKeyboardMarkup(inline_keyboard=buttons)

    @staticmethod
    def get_skip_keyboard():
        """Клавиатура с кнопкой пропуска"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭️ Пропустить", callback_data="skip")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
        ])

    @staticmethod
    def get_cancel_keyboard(callback_data: str = "cancel"):
        """Клавиатура отмены"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data=callback_data)]
        ])

    @staticmethod
    def get_back_button(callback_data: str = "back_to_main"):
        """Кнопка назад"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="↩️ Назад", callback_data=callback_data)]
        ])

    @staticmethod
    def get_refresh_keyboard(portfolio_id: int):
        """Клавиатура с обновлением"""
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить цены", callback_data=f"refresh_portfolio_{portfolio_id}")],
            [InlineKeyboardButton(text="↩️ Назад", callback_data=f"portfolio_{portfolio_id}")]
        ])

    @staticmethod
    def get_popular_tickers_page(page: int = 0, total_pages: int = 10):
        """Клавиатура для навигации по страницам популярных тикеров"""
        buttons = []

        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pop_page_{page - 1}")
            )

        nav_buttons.append(
            InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="ignore")
        )

        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(text="➡️ Вперед", callback_data=f"pop_page_{page + 1}")
            )

        if nav_buttons:
            buttons.append(nav_buttons)

        buttons.append([InlineKeyboardButton(text="↩️ Главное меню", callback_data="back_to_main")])

        return InlineKeyboardMarkup(inline_keyboard=buttons)