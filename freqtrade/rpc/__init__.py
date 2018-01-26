import logging
import re
import arrow
from decimal import Decimal
from datetime import datetime, timedelta
from pandas import DataFrame
import sqlalchemy as sql

from freqtrade.persistence import Trade
from freqtrade.misc import State, get_state
from freqtrade import exchange
from freqtrade.fiat_convert import CryptoToFiatConverter
from . import telegram

logger = logging.getLogger(__name__)


REGISTERED_MODULES = []


def init(config: dict) -> None:
    """
    Initializes all enabled rpc modules
    :param config: config to use
    :return: None
    """

    if config['telegram'].get('enabled', False):
        logger.info('Enabling rpc.telegram ...')
        REGISTERED_MODULES.append('telegram')
        telegram.init(config)


def cleanup() -> None:
    """
    Stops all enabled rpc modules
    :return: None
    """
    if 'telegram' in REGISTERED_MODULES:
        logger.debug('Cleaning up rpc.telegram ...')
        telegram.cleanup()


def send_msg(msg: str) -> None:
    """
    Send given markdown message to all registered rpc modules
    :param msg: message
    :return: None
    """
    logger.info(msg)
    if 'telegram' in REGISTERED_MODULES:
        telegram.send_msg(msg)


def shorten_date(_date):
    """
    Trim the date so it fits on small screens
    """
    new_date = re.sub('seconds?', 'sec', _date)
    new_date = re.sub('minutes?', 'min', new_date)
    new_date = re.sub('hours?', 'h', new_date)
    new_date = re.sub('days?', 'd', new_date)
    new_date = re.sub('^an?', '1', new_date)
    return new_date


#
# Below follows the RPC backend
# it is prefixed with rpc_
# to raise awareness that it is
# a remotely exposed function


def rpc_trade_status():
    # Fetch open trade
    trades = Trade.query.filter(Trade.is_open.is_(True)).all()
    if get_state() != State.RUNNING:
        return (True, '*Status:* `trader is not running`')
    elif not trades:
        return (True, '*Status:* `no active trade`')
    else:
        result = []
        for trade in trades:
            order = None
            if trade.open_order_id:
                order = exchange.get_order(trade.open_order_id)
            # calculate profit and send message to user
            current_rate = exchange.get_ticker(trade.pair, False)['bid']
            current_profit = trade.calc_profit_percent(current_rate)
            fmt_close_profit = '{:.2f}%'.format(
                round(trade.close_profit * 100, 2)
            ) if trade.close_profit else None
            message = """
*Trade ID:* `{trade_id}`
*Current Pair:* [{pair}]({market_url})
*Open Since:* `{date}`
*Amount:* `{amount}`
*Open Rate:* `{open_rate:.8f}`
*Close Rate:* `{close_rate}`
*Current Rate:* `{current_rate:.8f}`
*Close Profit:* `{close_profit}`
*Current Profit:* `{current_profit:.2f}%`
*Open Order:* `{open_order}`
            """.format(
                trade_id=trade.id,
                pair=trade.pair,
                market_url=exchange.get_pair_detail_url(trade.pair),
                date=arrow.get(trade.open_date).humanize(),
                open_rate=trade.open_rate,
                close_rate=trade.close_rate,
                current_rate=current_rate,
                amount=round(trade.amount, 8),
                close_profit=fmt_close_profit,
                current_profit=round(current_profit * 100, 2),
                open_order='({} rem={:.8f})'.format(
                    order['type'], order['remaining']
                ) if order else None,
            )
            result.append(message)
        return (False, result)


def rpc_status_table():
    trades = Trade.query.filter(Trade.is_open.is_(True)).all()
    if get_state() != State.RUNNING:
        return (True, '*Status:* `trader is not running`')
    elif not trades:
        return (True, '*Status:* `no active order`')
    else:
        trades_list = []
        for trade in trades:
            # calculate profit and send message to user
            current_rate = exchange.get_ticker(trade.pair, False)['bid']
            trades_list.append([
                trade.id,
                trade.pair,
                shorten_date(arrow.get(trade.open_date).humanize(only_distance=True)),
                '{:.2f}%'.format(100 * trade.calc_profit_percent(current_rate))
            ])

        columns = ['ID', 'Pair', 'Since', 'Profit']
        df_statuses = DataFrame.from_records(trades_list, columns=columns)
        df_statuses = df_statuses.set_index(columns[0])
        # The style used throughout is to return a tuple
        # consisting of (error_occured?, result)
        # Another approach would be to just return the
        # result, or raise error
        return (False, df_statuses)


def rpc_daily_profit(timescale, stake_currency, fiat_display_currency):
    today = datetime.utcnow().date()
    profit_days = {}

    if not (isinstance(timescale, int) and timescale > 0):
        return (True, '*Daily [n]:* `must be an integer greater than 0`')

    fiat = CryptoToFiatConverter()
    for day in range(0, timescale):
        profitday = today - timedelta(days=day)
        trades = Trade.query \
            .filter(Trade.is_open.is_(False)) \
            .filter(Trade.close_date >= profitday)\
            .filter(Trade.close_date < (profitday + timedelta(days=1)))\
            .order_by(Trade.close_date)\
            .all()
        curdayprofit = sum(trade.calc_profit() for trade in trades)
        profit_days[profitday] = {
            'amount': format(curdayprofit, '.8f'),
            'trades': len(trades)
        }

    stats = [
        [
            key,
            '{value:.8f} {symbol}'.format(
                value=float(value['amount']),
                symbol=stake_currency
            ),
            '{value:.3f} {symbol}'.format(
                value=fiat.convert_amount(
                    value['amount'],
                    stake_currency,
                    fiat_display_currency
                ),
                symbol=fiat_display_currency
            ),
            '{value} trade{s}'.format(value=value['trades'], s='' if value['trades'] < 2 else 's'),
        ]
        for key, value in profit_days.items()
    ]
    return (False, stats)


def rpc_trade_statistics(stake_currency, fiat_display_currency) -> None:
    """
    :return: cumulative profit statistics.
    """
    trades = Trade.query.order_by(Trade.id).all()

    profit_all_coin = []
    profit_all_percent = []
    profit_closed_coin = []
    profit_closed_percent = []
    durations = []

    for trade in trades:
        current_rate = None

        if not trade.open_rate:
            continue
        if trade.close_date:
            durations.append((trade.close_date - trade.open_date).total_seconds())

        if not trade.is_open:
            profit_percent = trade.calc_profit_percent()
            profit_closed_coin.append(trade.calc_profit())
            profit_closed_percent.append(profit_percent)
        else:
            # Get current rate
            current_rate = exchange.get_ticker(trade.pair, False)['bid']
            profit_percent = trade.calc_profit_percent(rate=current_rate)

        profit_all_coin.append(trade.calc_profit(rate=Decimal(trade.close_rate or current_rate)))
        profit_all_percent.append(profit_percent)

    best_pair = Trade.session.query(Trade.pair,
                                    sql.func.sum(Trade.close_profit).label('profit_sum')) \
        .filter(Trade.is_open.is_(False)) \
        .group_by(Trade.pair) \
        .order_by(sql.text('profit_sum DESC')) \
        .first()

    if not best_pair:
        return (True, '*Status:* `no closed trade`')

    bp_pair, bp_rate = best_pair

    # FIX: we want to keep fiatconverter in a state/environment,
    #      doing this will utilize its caching functionallity, instead we reinitialize it here
    fiat = CryptoToFiatConverter()
    # Prepare data to display
    profit_closed_coin = round(sum(profit_closed_coin), 8)
    profit_closed_percent = round(sum(profit_closed_percent) * 100, 2)
    profit_closed_fiat = fiat.convert_amount(
        profit_closed_coin,
        stake_currency,
        fiat_display_currency
    )
    profit_all_coin = round(sum(profit_all_coin), 8)
    profit_all_percent = round(sum(profit_all_percent) * 100, 2)
    profit_all_fiat = fiat.convert_amount(
        profit_all_coin,
        stake_currency,
        fiat_display_currency
    )
    return (False,
            {'profit_closed_coin': profit_closed_coin,
             'profit_closed_percent': profit_closed_percent,
             'profit_closed_fiat': profit_closed_fiat,
             'profit_all_coin': profit_all_coin,
             'profit_all_percent': profit_all_percent,
             'profit_all_fiat': profit_all_fiat,
             'trade_count': len(trades),
             'first_trade_date': arrow.get(trades[0].open_date).humanize(),
             'latest_trade_date': arrow.get(trades[-1].open_date).humanize(),
             'avg_duration': str(timedelta(seconds=sum(durations) /
                                           float(len(durations)))).split('.')[0],
             'best_pair': bp_pair,
             'best_rate': round(bp_rate * 100, 2)
             })

    # Message to display
    markdown_msg = """
*ROI:* Close trades
  ∙ `{profit_closed_coin:.8f} {coin} ({profit_closed_percent:.2f}%)`
  ∙ `{profit_closed_fiat:.3f} {fiat}`
*ROI:* All trades
  ∙ `{profit_all_coin:.8f} {coin} ({profit_all_percent:.2f}%)`
  ∙ `{profit_all_fiat:.3f} {fiat}`

*Total Trade Count:* `{trade_count}`
*First Trade opened:* `{first_trade_date}`
*Latest Trade opened:* `{latest_trade_date}`
*Avg. Duration:* `{avg_duration}`
*Best Performing:* `{best_pair}: {best_rate:.2f}%`
    """.format(
        coin=stake_currency,
        fiat=fiat_display_currency,
        profit_closed_coin=profit_closed_coin,
        profit_closed_percent=profit_closed_percent,
        profit_closed_fiat=profit_closed_fiat,
        profit_all_coin=profit_all_coin,
        profit_all_percent=profit_all_percent,
        profit_all_fiat=profit_all_fiat,
        trade_count=len(trades),
        first_trade_date=arrow.get(trades[0].open_date).humanize(),
        latest_trade_date=arrow.get(trades[-1].open_date).humanize(),
        avg_duration=str(timedelta(seconds=sum(durations) / float(len(durations)))).split('.')[0],
        best_pair=bp_pair,
        best_rate=round(bp_rate * 100, 2),
    )
    return markdown_msg


def rpc_balance(fiat_display_currency):
    """
    :return: current account balance per crypto
    """
    balances = [
        c for c in exchange.get_balances()
        if c['Balance'] or c['Available'] or c['Pending']
    ]
    if not balances:
        return (True, '`All balances are zero.`')

    output = []
    total = 0.0
    for currency in balances:
        coin = currency['Currency']
        if coin == 'BTC':
            currency["Rate"] = 1.0
        else:
            currency["Rate"] = exchange.get_ticker('BTC_' + coin, False)['bid']
        currency['BTC'] = currency["Rate"] * currency["Balance"]
        total = total + currency['BTC']
        output.append({'currency': currency['Currency'],
                       'available': currency['Available'],
                       'balance': currency['Balance'],
                       'pending': currency['Pending'],
                       'est_btc': currency['BTC']
                       })
    fiat = CryptoToFiatConverter()
    symbol = fiat_display_currency
    value = fiat.convert_amount(total, 'BTC', symbol)
    return (False, (output, total, symbol, value))
