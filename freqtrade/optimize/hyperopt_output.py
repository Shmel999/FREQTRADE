import sys
from typing import List, Optional, Union

from rich.console import Console
from rich.table import Table
from rich.text import Text

from freqtrade.constants import Config
from freqtrade.optimize.optimize_reports import generate_wins_draws_losses
from freqtrade.util import fmt_coin


class HyperoptOutput:
    def __init__(self):
        self._table = Table(
            title="Hyperopt results",
        )
        # Headers
        self._table.add_column("Best", justify="left")
        self._table.add_column("Epoch", justify="right")
        self._table.add_column("Trades", justify="right")
        self._table.add_column("Win  Draw  Loss  Win%", justify="right")
        self._table.add_column("Avg profit", justify="right")
        self._table.add_column("Profit", justify="right")
        self._table.add_column("Avg duration", justify="right")
        self._table.add_column("Objective", justify="right")
        self._table.add_column("Max Drawdown (Acct)", justify="right")

    def _add_row(self, data: List[Union[str, Text]]):
        """Add single row"""
        row_to_add: List[Union[str, Text]] = [r if isinstance(r, Text) else str(r) for r in data]

        self._table.add_row(*row_to_add)

    def _add_rows(self, data: List[List[Union[str, Text]]]):
        """add multiple rows"""
        for row in data:
            self._add_row(row)

    def print(self, console: Optional[Console] = None, *, print_colorized=True):
        if not console:
            console = Console(
                color_system="auto" if print_colorized else None,
                width=200 if "pytest" in sys.modules else None,
            )

        console.print(self._table)

    def add_data(
        self,
        config: Config,
        results: list,
        total_epochs: int,
        highlight_best: bool,
    ) -> str:
        """Format one or multiple rows and add them"""
        stake_currency = config["stake_currency"]

        res = [
            [
                # "Best":
                (
                    ("*" if r["is_initial_point"] or r["is_random"] else "")
                    + (" Best" if r["is_best"] else "")
                ).lstrip(),
                # "Epoch":
                f"{r['current_epoch']}/{total_epochs}",
                # "Trades":
                r["results_metrics"]["total_trades"],
                # "Win  Draw  Loss  Win%":
                generate_wins_draws_losses(
                    r["results_metrics"]["wins"],
                    r["results_metrics"]["draws"],
                    r["results_metrics"]["losses"],
                ),
                # "Avg profit":
                f"{r['results_metrics']['profit_mean']:.2%}",
                # "Profit":
                "{} {}".format(
                    fmt_coin(
                        r["results_metrics"]["profit_total_abs"],
                        stake_currency,
                        keep_trailing_zeros=True,
                    ),
                    f"({r['results_metrics']['profit_total']:,.2%})".rjust(10, " "),
                )
                if r["results_metrics"]["profit_total_abs"] != 0.0
                else "--",
                # "Avg duration":
                r["results_metrics"]["holding_avg"],
                # "Objective":
                f"{r["loss"]:,.5f}" if r["loss"] != 100000 else "N/A",
                # "Max Drawdown (Acct)":
                "{} {}".format(
                    fmt_coin(
                        r["results_metrics"]["max_drawdown_abs"],
                        stake_currency,
                        keep_trailing_zeros=True,
                    ),
                    (f"({r["results_metrics"]['max_drawdown_account']:,.2%})").rjust(10, " "),
                )
                if r["results_metrics"]["max_drawdown_account"] != 0.0
                else "--",
            ]
            for r in results
        ]
        self._add_rows(res)