from utils import get_rapid_progress_live, exists_lichess_account
import dash
import platform
from dash.dependencies import Input, Output, State

from dash import dcc
from dash import html

from dateutil.relativedelta import relativedelta

import flask
from numpy.core.numeric import roll
import pandas as pd
import time

import configparser


import os
import plotly.express as px
import mysql.connector as mysql
from dash import dash_table
import numpy as np

import datetime
from datetime import date

import dash_bootstrap_components as dbc

import plotly.graph_objs as go
import logging

logging.basicConfig(level=logging.INFO, force=True)

server = flask.Flask("app")
# server.secret_key = os.environ.get('secret_key', 'secret')


def avg_cp_loss(sline, max_move, white):
    # cut list if max_move is set

    sline = sline.split(",")

    if max_move is not None:
        sline = sline[: 2 * max_move]

    # replace FILL with last value

    sline = [float(x) if x != "FILL" else np.nan for x in sline]

    sline = pd.Series(sline).ffill().to_list()

    np_list = np.array(sline)
    shift_list = np_list[1:]

    difflist = np_list[:-1] - shift_list

    if white:
        return int((np.abs(difflist[::2]).mean() * 100))

    return int((np.abs(difflist[1::2]).mean() * 100))


def assign_daytime(ts):
    if ts.hour < 6:
        return "night"
    if ts.hour < 12:
        return "morning"
    if ts.hour < 18:
        return "afternoon"
    return "evening"


home_dir = "" if platform.system() == "Windows" else "/app/"

print("HOME_DIR", home_dir, platform.system())

# frame_dict = {}

config = configparser.ConfigParser()
config.read(f"{home_dir}general.conf")
cc = config["DEFAULT"]

# players = cc["PLAYERS_SF"].split(",")
# players = sorted(players)

# for p in players:
#   try:
#      frame_dict[p] = ""
# except:
#    pass


# DEBUG

# df = df[df[""]]


"""
Lichess time controls are based on estimated game duration = (clock initial time) + 40  (clock increment)
For instance, the estimated duration of a 5+3 game is 5  60 + 40  3 = 420 seconds.

< 29s = UltraBullet
< 179s = Bullet
< 479s = Blitz
< 1499s = Rapid
 1500s = Classical
"""


def unix_time_millis(datetimevalue):
    return datetimevalue.timestamp()


def get_marks_from_start_end(start, end):
    """Returns dict with one item per month
    {1440080188.1900003: '2015-08',
    """

    rd = relativedelta(months=1)
    td_seconds = (end - start).total_seconds()

    # smaller than 15 months
    if td_seconds / 60 / 60 / 24 / 30 <= 15:
        rd = relativedelta(months=1)
    elif td_seconds / 60 / 60 / 24 / 30 <= 36:
        rd = relativedelta(months=2)
    else:
        rd = relativedelta(months=6)

    result = []
    current = start
    while current <= end:
        result.append(current)
        current += rd
    # print({unix_time_millis(m):(str(m.strftime('%Y-%m'))) for m in result})
    return {int(unix_time_millis(m)): (str(m.strftime("%Y-%m-%d"))) for m in result}

    # 0: {'label': '0°C', 'style': {'color': '#77b0b1'}},
    # return {int(unix_time_millis(m)):{'label':(str(m.strftime('%Y-%m-%d'))), 'style': {'color':'black'}} for m in result}


# playtime increment


app = dash.Dash("app", server=server)

app.scripts.config.serve_locally = True
# dcc._js_dist[0]['external_url'] = 'https://cdn.plot.ly/plotly-basic-latest.min.js'


external_stylesheets = [dbc.themes.BOOTSTRAP]


tabs_styles = {"height": "44px"}
tab_style = {
    "borderBottom": "1px solid #d6d6d6",
    "padding": "6px",
    "fontWeight": "bold",
}

tab_selected_style = {
    "borderTop": "1px solid #d6d6d6",
    "borderBottom": "1px solid #d6d6d6",
    "backgroundColor": "#119DFF",
    "color": "white",
    "padding": "6px",
}

# default player
# selected_player = frame_dict["fettarmqp"]

app.layout = html.Div(
    [
        html.H1("Chess Rating Compare"),
        html.P("You can compare multiple chess ratings of players here."),
        html.P(
            [
                "Enter the name of the lichess account(s) and select an appropriate time control.Click submit.",
                html.Br(),
                "Click submit.",
            ]
        ),
        html.P(
            [
                "If the account never got analyzed it will take some time (1-2 minutes) to load the data initially.",
                html.Br(),
                "Further requests in the future will reload much faster so be pacient.",
            ]
        ),
        dcc.Loading(
            id="loading-1",
            children=[
                dcc.Textarea(
                    id="input-field",
                    placeholder="Enter a lichess account(s)",
                    style={"width": 400, "height": 150},
                ),
                html.Div(id="output-container"),
                html.Div(id="hidden-data", style={"display": "none"}),
                # html.Div(
                #    [
                #        html.Span("Choose name", style={"font-weight": "bold"}),
                #        dcc.Dropdown(
                #            id="input-player",
                #            options=[{"label": x, "value": x} for x in ["fettarmqp"]],
                #            value="fettarmqp",
                #            className="dash-bootstrap",
                #            multi=True,
                #        ),
                #    ],
                #    style={"width": "20%", "margin": "auto", "margin-bottom": "20px"},
                # ),
                html.Div(
                    [
                        html.Span("Choose time control", style={"font-weight": "bold"}),
                        dcc.Dropdown(
                            id="dropdown-timecontrol",
                            options=[
                                {"label": "Blitz", "value": "Blitz"},
                                {"label": "Rapid", "value": "Rapid"},
                                {"label": "Classical", "value": "Classical"},
                            ],
                            value="Rapid",
                            className="dash-bootstrap",
                        ),
                    ],
                    style={"width": "20%", "margin": "auto", "margin-bottom": "20px"},
                ),
                html.Div(
                    [
                        html.Button("Submit", id="submit-button", n_clicks=0),
                    ]
                ),
                # html.Div([
                #    dcc.RangeSlider(
                #    id='time-slider',
                #    #min=unix_time_millis(selected_player["PlayedOn"].min()),
                #    #max=unix_time_millis(selected_player["PlayedOn"].max()),
                #    #value=[unix_time_millis(selected_player["PlayedOn"].min()), unix_time_millis(selected_player["PlayedOn"].max())],
                #    #marks=get_marks_from_start_end(selected_player["PlayedOn"].min(), selected_player["PlayedOn"].max()),
                #    #tooltip={"placement": "bottom", "always_visible": True}
                #    className="dash-bootstrap"
                #    ),
                #    html.Div(id='output-container-range-slider')
                # ]),
                # html.Div(
                #    [
                #        dcc.DatePickerRange(
                #            id="date-picker",
                # min_date_allowed=date(2021, 1, 1),
                # max_date_allowed=date(2021, 6, 1),
                # initial_visible_month=date(2021, 8, 5),
                # start_date=date(2020, 8, 25),
                # end_date=date(2021,1,1),
                #            display_format="YYYY-MM-DD",
                #            className="dash-bootstrap",
                #        ),
                #    ],
                #    style={"width": "30%", "margin": "auto", "margin-bottom": "20px"},
                # ),
                html.Br(),
                dcc.Graph(id="graph-elo", className="container"),
            ],
        ),
        # ], )
    ],
    className="container",
    style={"margin": "auto", "text-align": "center", "width": "80%"},
)

"""
        min_date_allowed=date(2021, 1, 1),
        max_date_allowed=date(2021, 6, 1),
        initial_visible_month=date(2021, 8, 5),
        start_date=date(2020, 8, 25),
        end_date=date(2021,1,1),
        # """

names = []
button_ids = []


@app.callback(
    Output("graph-elo", "figure"),
    [Input("submit-button", "n_clicks"), Input("dropdown-timecontrol", "value")],
    [State("input-field", "value")],
)
def update_graph_elo(n_clicks, time_control, player_names):
    if n_clicks is None:
        return

    # min_date = datetime.datetime.strptime(min_date, "%Y-%m-%d")
    # max_date = datetime.datetime.strptime(max_date, "%Y-%m-%d")

    player_names = [x.strip() for x in player_names.split(",")]

    # filter
    player_names = [x for x in player_names if exists_lichess_account(x)]

    print(f"list content {player_names}")
    df = pd.DataFrame()

    for name in player_names:
        print(f" iterating over {name}")
        # df2 = get_rapid_progress(name, time_control)
        df2 = get_rapid_progress_live(name, time_control)
        if len(df) > 0:
            df = df.join(df2, how="outer")
        else:
            df = df2.copy()

    df = df.reset_index()

    elo_cols = [x for x in df.columns if "elo" in x]

    logging.info(f"Columns {df.columns}")

    fig = px.line(df.iloc[15:], x="game_number", y=elo_cols)

    fig.update_layout(
        yaxis=dict(
            title_text="rating progress",
            titlefont=dict(size=15),
        ),
        xaxis=dict(title_text="Number of games"),
        title={
            "text": "Rating gained over number of games played",
            #'y':0.96,
            "x": 0.5,
            "xanchor": "center",
            "yanchor": "top",
        },
        template="plotly_dark",
    )

    return fig


if __name__ == "__main__":
    app.run_server(host="0.0.0.0")
