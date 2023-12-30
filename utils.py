import mysql.connector as cn
import pandas as pd
import configparser
import platform
import datetime
import pickle
import logging
import requests
import os


# test


def exists_lichess_account(name):
    url = "https://lichess.org/api/users"
    r = requests.post(url, data=name)
    return len(r.json()) > 0


def get_config():
    home_dir = "" if platform.system() == "Windows" else "/app/"
    config = configparser.ConfigParser()
    config.read(f"{home_dir}general.conf")
    cc = config["DEFAULT"]
    return cc


def get_connection():
    cc = get_config()

    return cn.connect(
        host=cc["HOST"],
        user=cc["USER"],
        password=cc["PASSWORD"],
        database=cc["DATABASE"],
    )


def timecontrol_classifier(playtime, increment):
    estimated_game_duration = playtime + 40 * increment

    if estimated_game_duration < 29:
        return "UltraBullet"
    if estimated_game_duration < 179:
        return "Bullet"
    if estimated_game_duration < 479:
        return "Blitz"
    if estimated_game_duration < 1499:
        return "Rapid"
    return "Classical"


def pgn_entry_parser(line):
    line = line[1:-1]
    pos = line.find(" ")

    return [line[:pos], line[pos + 1 :].replace('"', "")]


def pgn_parser(pgn):
    y = list(map(pgn_entry_parser, pgn.split("\n")))

    return {x[0]: x[1] for x in y}


def get_rapid_progress_live(username, time_control):
    config = get_config()
    custom_format_to = "%Y-%m-%d %H:%M:%S"

    pickle_filename = f"snapshots/{username.lower()}_{time_control.lower()}games.pickle"
    elo_column = f"{username}_elo"

    last_game = "1999-01-01 00:00:00"

    # load existing pickle

    df_existing = None

    mtime = 0

    try:
        with open(pickle_filename, "rb") as f:
            df_existing = pickle.load(f)
        last_game = df_existing["PlayedOn"].max() + datetime.timedelta(seconds=30)
        last_game = last_game.strftime(custom_format_to)
        mtime = int(os.path.getmtime(pickle_filename)) * 1000
    except:
        pass

    datetime.datetime.strptime(last_game, custom_format_to)
    last_game_converted = (
        int(datetime.datetime.strptime(last_game, custom_format_to).timestamp()) * 1000
    )

    now_converted = int(datetime.datetime.now().timestamp() * 1000)

    df = None

    limit = 3600 * 24 * 1000
    time_diff = now_converted - mtime

    logging.info(
        f"now {now_converted} mtime {mtime} diff {time_diff} THRESH {limit} COMP {now_converted - last_game_converted >= 3600 * 24 * 1000}"
    )

    if time_diff >= limit:
        url = f"https://lichess.org/api/games/user/{username}?rated=true&perfType={time_control.lower()}&moves=false&since={last_game_converted}&sort=dateAsc"

        logging.info(f"Calling URL {url}")

        token = config["APP_TOKEN"]

        header = {"Authorization": f"Bearer {token}"}

        r = requests.get(url, stream=True, headers=header)

        pgn = ""
        pgns = list()

        for line in r.iter_lines():
            pgn += line.decode() + "\n"

            if pgn.endswith("\n\n"):
                pgns.append(pgn)
                print(".", end="")
                pgn = ""

        pp = [pgn_parser(x) for x in pgns if len(x) > 10]

        df = pd.DataFrame().from_dict(pp)

        df["PlayedOn"] = df.apply(lambda x: x["UTCDate"] + " " + x["UTCTime"], axis=1)
        df["PlayedOn"] = pd.to_datetime(df["PlayedOn"], format="%Y.%m.%d %H:%M:%S")

        df[elo_column] = df.apply(
            lambda x: int(x["WhiteElo"])
            if x["White"].lower() == username.lower()
            else int(x["BlackElo"]),
            axis=1,
        )

        df = df.drop(
            [
                "Event",
                "UTCDate",
                "UTCTime",
                "Variant",
                "ECO",
                "Termination",
                "",
                "White",
                "Black",
                "Result",
                "BlackElo",
                "WhiteElo",
                "WhiteRatingDiff",
                "BlackRatingDiff",
                "TimeControl",
                "Date",
            ],
            axis=1,
        )

        try:
            df = df.drop(["BlackTitle"], axis=1)
            df = df.drop(["WhiteTitle"], axis=1)
        except:
            pass

        if df_existing is not None:
            # merge

            df = pd.concat([df, df_existing])

        with open(pickle_filename, "wb") as f:
            pickle.dump(df, f)

    else:
        logging.info(f"skipping {username}")
        df = df_existing

    df = df.sort_values("PlayedOn").drop_duplicates()

    df["game_number"] = range(1, len(df) + 1)

    return df[[elo_column, "game_number"]].set_index("game_number")


def get_rapid_progress(username, time_control):
    cnx = get_connection()

    query = (
        "SELECT b.PlayedOn, playtime, increment, black, white, blackelo_pre, whiteelo_pre "
        "FROM parsedgames2 as a "
        "join rawgames as b "
        "  on a.gameid = b.gameid "
        f"where (black = '{username}'"
        f" or white = '{username}') and rated=1 "
    )

    df = pd.read_sql(query, cnx)

    df["time_control"] = df.apply(
        lambda x: timecontrol_classifier(x["playtime"], x["increment"]), axis=1
    )

    df = df[df["time_control"] == time_control].drop(
        ["time_control", "playtime", "increment"], axis=1
    )

    elo_column = f"{username}_elo"
    df[elo_column] = df.apply(
        lambda x: x["whiteelo_pre"]
        if x["white"].lower() == username.lower()
        else x["blackelo_pre"],
        axis=1,
    )
    df = df[["PlayedOn", elo_column]].sort_values("PlayedOn")

    df["game_number"] = range(1, len(df) + 1)

    return df[[elo_column, "game_number"]].set_index("game_number")
