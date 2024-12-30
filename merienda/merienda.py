"""Welcome to Reflex! This file outlines the steps to create a basic app."""

import asyncio
import datetime
from enum import Enum

import reflex as rx
from tapo import ApiClient
from tapo.requests import EnergyDataInterval

from rxconfig import config

from .cfg import get_cfg

_client = ApiClient(get_cfg().tapo_username, get_cfg().tapo_password, timeout_s=10)


class _CarState(Enum):
    PLUGGED = 1
    UNPLUGGED = 2
    CHARGING = 3
    CHARGED = 4


class State(rx.State):
    """The app state."""

    initialized: bool = False

    plug_curr_watt: int = 0
    plug_is_on: bool = False
    plug_last_known_on: datetime.datetime = datetime.datetime.now()
    plug_last_poll: datetime.datetime = datetime.datetime.now()
    plug_last_watt_day: list[int]

    @rx.event(background=True)
    async def poll_plug(self):
        print("Polling plug")
        plug = await _client.p115(get_cfg().tapo_ip)
        print("Connected to plug")
        last_conn = datetime.datetime.now()

        while True:
            async with self:
                power = await plug.get_current_power()
                self.plug_curr_watt = power.current_power + 1

                status = await plug.get_device_info()
                if (
                    not self.plug_is_on and status.device_on
                ):  # update last known device_on time
                    self.plug_last_known_on = datetime.datetime.now()

                self.plug_is_on = status.device_on

                last = await plug.get_energy_data(
                    EnergyDataInterval.Hourly,
                    start_date=datetime.datetime.now() - datetime.timedelta(days=1),
                    end_date=datetime.datetime.now(),
                )
                self.plug_last_watt_day = last.data

                self.plug_last_poll = datetime.datetime.now()

                if self.plug_is_on and False:  # debug block
                    import random

                    self.plug_curr_watt = random.randint(10 * 130 - 20, 10 * 130 + 20)
                    self.plug_last_watt_day[-1] = int(10 * 130 * 0.33 / 1000 * n_iters)
            await asyncio.sleep(get_cfg().polling_rate_s)

            if datetime.datetime.now() - last_conn > datetime.timedelta(minutes=30):
                plug = await _client.p115(
                    get_cfg().tapo_ip
                )  # reconnect every 30 minutes
                last_conn = datetime.datetime.now()

    async def toggle_dev(self):
        print(f"Toggling device from {self.plug_is_on} to {not self.plug_is_on}")
        curr_state = self.plug_is_on
        self.plug_is_on = not self.plug_is_on
        plug = await _client.p115(get_cfg().tapo_ip)
        await plug.on() if not curr_state else await plug.off()

    @rx.var
    def last_24h_watts(self) -> int:
        return sum(self.plug_last_watt_day)

    @rx.var
    def last_24h_cost(self) -> float:
        return round(self.last_24h_watts / 1000 * get_cfg().price_per_kw_eur, 3)

    @rx.var
    def is_charging(self) -> bool:
        return self.plug_is_on and self.plug_curr_watt > 100

    @rx.var
    def get_car_state(self) -> _CarState:
        if self.plug_is_on and self.plug_curr_watt > 100:  # some current
            return _CarState.CHARGING

        if (
            self.plug_is_on
            and self.plug_curr_watt < 100
            and self.last_24h_watts > get_cfg().total_capacity_wh * 0.8
        ):
            return _CarState.CHARGED

        if not self.plug_is_on:
            return _CarState.UNPLUGGED

        return _CarState.PLUGGED

    @rx.var
    def is_charged(self) -> bool:
        return (
            self.plug_is_on and self.plug_curr_watt < 100 and self.last_24h_watts > 8000
        )

    @rx.var()
    def time_last_update(self) -> str:
        return self.plug_last_poll.strftime("%H:%M:%S")

    @rx.var
    def get_car_resource(self) -> str:
        match self.get_car_state:
            case _CarState.CHARGING:
                return "/cars/car_orange.png"
            case _CarState.CHARGED:
                return "/cars/car_green.png"
            case _:
                return "/cars/car_default.png"

    def _calc_estimated_percent(self, from_percent: float) -> tuple[float, str]:
        initial_charge = (
            from_percent * get_cfg().total_capacity_wh
        )  # wh that had the car before charging

        estimated_charge = initial_charge + self.last_24h_watts

        percent = min(1, estimated_charge / get_cfg().total_capacity_wh)

        remaining_time = datetime.timedelta(
            seconds=(get_cfg().total_capacity_wh - estimated_charge)
            / max(1, self.plug_curr_watt)
            * 3600
        )

        return percent, _pretty_delta(remaining_time)

    @rx.var
    def calc_estimated_percent_20(self) -> tuple[float, str]:
        return self._calc_estimated_percent(0.2)

    @rx.var
    def calc_estimated_percent_0(self) -> tuple[float, str]:
        return self._calc_estimated_percent(0)


def _pretty_delta(delta: datetime.timedelta) -> str:
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _remaining_box(
    from_percent: float,
    est_percent: float,
    remaining_msg: str,
):
    return rx.tooltip(
        rx.card(
            rx.heading(rx.text((from_percent * 100) // 1, "%"), size="3"),
            rx.cond(
                State.is_charging,
                rx.box(
                    rx.text("Carga: ", (est_percent * 100) // 1, "%"),
                    rx.text("T. rest.: ", remaining_msg),
                ),
                rx.box(
                    rx.text(
                        "Carga: --",
                    ),
                    rx.text(
                        "T. rest.: --",
                    ),
                ),
            ),
        ),
        content=f"Estimación al enchufar el coche con {from_percent * 100:.0f}% de carga",
    )


def status_row():
    return rx.cond(
        State.get_car_state == _CarState.CHARGING,
        rx.hstack(
            rx.text(
                "Cargando el vehículo a ",
                rx.text.strong(State.plug_curr_watt),
                "w/h",
            ),
        ),
        rx.cond(
            State.get_car_state == _CarState.CHARGED,
            rx.text("Vehículo cargado"),
            rx.cond(
                State.get_car_state == _CarState.UNPLUGGED,
                rx.text("Vehículo desconectado"),
                rx.text("Vehículo conectado"),
            ),
        ),
    )


def index() -> rx.Component:
    # Welcome Page (Index)
    return rx.container(
        rx.heading(rx.text("Estado de la carga del José")),
        status_row(),
        rx.grid(
            rx.card(
                rx.heading("Últimas 24h", size="3"),
                rx.text(
                    f"{State.last_24h_cost:.2f}€",
                ),
                rx.text(
                    f"{State.last_24h_watts}w",
                ),
            ),
            _remaining_box(
                0,
                State.calc_estimated_percent_0[0],
                State.calc_estimated_percent_0[1],
            ),
            _remaining_box(
                0.2,
                State.calc_estimated_percent_20[0],
                State.calc_estimated_percent_20[1],
            ),
            columns="3",
            justify="between",
            align="center",
            spacing="4",
        ),
        rx.hstack(
            rx.button(
                rx.cond(State.plug_is_on, "Detener Carga", "Iniciar Carga"),
                on_click=State.toggle_dev,
                color_scheme=rx.cond(
                    State.plug_is_on,
                    "tomato",
                    "teal",
                ),
                flex=1,
            ),
            rx.image(State.get_car_resource, height="100%"),
            align="center",
            height="50px",
        ),
        rx.text(State.time_last_update, opacity=0.2, size="1", text_align="end"),
        spacing="4",
    )


app = rx.App()
app.add_page(index, on_load=State.poll_plug)
