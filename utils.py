import mysql.connector as cn
import pandas as pd
import configparser


def get_connection():
    home_dir = "/app/"
    config = configparser.ConfigParser()
    config.read(f"{home_dir}general.conf")
    cc = config["DEFAULT"]

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
