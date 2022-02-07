import datetime
import os
import time
import tempfile
import requests
import subprocess
from math import log, floor
from requests import ConnectionError
from requests import HTTPError
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from pyrogram.errors.exceptions import MessageIdInvalid
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid, MessageNotModified
from logging2 import Logger
import psutil
import custom_filters
import qbittorrent_control
from check_finished_torrents import checkTorrents
from config import API_ID, API_HASH, TG_TOKEN, AUTHORIZED_IDS
import db_management

logger = Logger(__name__)
app = Client("qbittorrent_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TG_TOKEN)
ngrok_api_url = ["http://127.0.0.1:4040/api/tunnels", "http://127.0.0.1:4050/api/tunnels"]
spammer = checkTorrents(app)
spammer.start()


def get_ngrok_info():
    max_retry = 10
    retry_count = 0
    sleep_sec = 20
    status_count = 0
    msg = ""
    while status_count != len(ngrok_api_url) and retry_count <= max_retry:
        time.sleep(sleep_sec)
        for url in ngrok_api_url:
            logger.info(f'fetching ngrok tunnel info: {url}')
            try:
                response = requests.get(url, headers={'Content-Type': 'application/json'})
            except (ConnectionError, HTTPError):
                logger.error(f'failed to connect: {url}')
            else:
                if response.status_code == 200:
                    status_count += 1
                    tunnels = response.json()["tunnels"]
                    for tunnel in tunnels:
                        msg += f'🚀 <b>Name:</b> <code>{tunnel["name"]}</code>\n'
                        msg += f'⚡ <b>URL:</b> {tunnel["public_url"]}\n\n'
                response.close()
        retry_count += 1
        if status_count == len(ngrok_api_url):
            break
    if retry_count > max_retry:
        logger.error("failed to get ngrok info on startup")
    else:
        for user_id in AUTHORIZED_IDS:
            try:
                app.send_message(user_id, msg, parse_mode="html")
            except PeerIdInvalid:
                logger.error(f"Failed to send ngrok info to {user_id}")


def convert_size(size_bytes) -> str:
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(floor(log(size_bytes, 1024)))
    p = pow(1024, i)
    s = round(size_bytes / p, 2)
    return "%s %s" % (s, size_name[i])


def convert_eta(n) -> str:
    return str(datetime.timedelta(seconds=n))


def send_menu(message, chat) -> None:
    logger.info(f"send_menu: {chat}")
    db_management.write_support("None", chat)
    buttons = [[InlineKeyboardButton("📝 List", "list")],
               [InlineKeyboardButton("➕ Add Magnet", "category#add_magnet"),
                InlineKeyboardButton("➕ Add Torrent", "category#add_torrent")],
               [InlineKeyboardButton("⏸ Pause", "pause"),
                InlineKeyboardButton("▶️ Resume", "resume")],
               [InlineKeyboardButton("⏸ Pause All", "pause_all"),
                InlineKeyboardButton("▶️ Resume All", "resume_all")],
               [InlineKeyboardButton("🗑 Delete", "delete_one"),
                InlineKeyboardButton("🗑 Delete All", "delete_all")],
               [InlineKeyboardButton("➕ Add Category", "add_category"),
                InlineKeyboardButton("🗑 Remove Category", "select_category#remove_category")],
               [InlineKeyboardButton("📝 Modify Category", "select_category#modify_category"),
                InlineKeyboardButton("🚦 System Info", "system_info")],
               [InlineKeyboardButton("🚀 Ngrok Info", "ngrok_info")]]

    try:
        app.edit_message_text(chat, message, text="Qbittorrent Control", reply_markup=InlineKeyboardMarkup(buttons))

    except MessageIdInvalid:
        app.send_message(chat, text="Qbittorrent Control", reply_markup=InlineKeyboardMarkup(buttons))


def list_active_torrents(n, chat, message, callback, status_filter: str = None) -> None:
    logger.info(f"list_active_torrents: {chat}")
    try:
        torrents = qbittorrent_control.get_torrent_info(status_filter=status_filter)
    except Exception:
        logger.error("Error in list_active_torrents")
        txt = "⚠️ <b>Some error occurred</b>"
        button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
        app.edit_message_text(chat, message, txt, parse_mode="html", reply_markup=button)
    else:
        def render_categories_buttons():
            return [
                InlineKeyboardButton(f"⏳ {'*' if status_filter == 'downloading' else ''} Downloading",
                                     "by_status_list#downloading"),
                InlineKeyboardButton(f"✔️ {'*' if status_filter == 'completed' else ''} Completed",
                                     "by_status_list#completed"),
                InlineKeyboardButton(f"⏸️ {'*' if status_filter == 'paused' else ''} Paused", "by_status_list#paused"),
            ]

        categories_buttons = render_categories_buttons()
        if not torrents:
            buttons = [categories_buttons, [InlineKeyboardButton("🔙 Menu", "menu")]]
            try:
                app.edit_message_text(chat, message, "There are no torrents", reply_markup=InlineKeyboardMarkup(buttons))
            except MessageIdInvalid:
                app.send_message(chat, "There are no torrents", reply_markup=InlineKeyboardMarkup(buttons))
            return

        buttons = [categories_buttons]

        if n == 1:
            for key, i in enumerate(torrents):
                buttons.append([InlineKeyboardButton(i.name, f"{callback}#{key+1}")])

            buttons.append([InlineKeyboardButton("🔙 Menu", "menu")])

            try:
                app.edit_message_reply_markup(chat, message, reply_markup=InlineKeyboardMarkup(buttons))
            except (MessageIdInvalid, MessageNotModified):
                app.send_message(chat, "Qbittorrent Control", reply_markup=InlineKeyboardMarkup(buttons))

        else:
            for key, i in enumerate(torrents):
                buttons.append([InlineKeyboardButton(i.name, f"torrentInfo#{key+1}")])

            buttons.append([InlineKeyboardButton("🔙 Menu", "menu")])

            try:
                app.edit_message_reply_markup(chat, message, reply_markup=InlineKeyboardMarkup(buttons))
            except (MessageIdInvalid, MessageNotModified):
                app.send_message(chat, "Qbittorrent Control", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_message(filters=filters.command("start"))
def start_command(client: Client, message: Message) -> None:
    logger.info(f"/start: {message.from_user.first_name}")
    """Start the bot."""
    if message.from_user.id in AUTHORIZED_IDS:
        send_menu(message.message_id, message.chat.id)

    else:
        button = InlineKeyboardMarkup([[InlineKeyboardButton("Github",
                                                             url="https://github.com/ch3p4ll3/QBittorrentBot/")]])
        app.send_message(message.chat.id, "You are not authorized to use this bot", reply_markup=button)


@app.on_callback_query(filters=custom_filters.system_info_filter)
def stats_command(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"/stats: {callback_query.from_user.first_name}")
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
    try:
        txt = f"**============SYSTEM============**\n" \
            f"**CPU Usage:** {psutil.cpu_percent(interval=None)}%\n" \
            f"**CPU Freq:** {psutil.cpu_freq(percpu=False).current} MHz\n" \
            f"**CPU Temp:** {psutil.sensors_temperatures()['cpu_thermal'][0].current}°C\n" \
            f"**Free Memory:** {convert_size(psutil.virtual_memory().available)} of " \
            f"{convert_size(psutil.virtual_memory().total)} ({psutil.virtual_memory().percent}%)\n" \
            f"**Disks usage:** {convert_size(psutil.disk_usage('/').used)} of " \
            f"{convert_size(psutil.disk_usage('/').total)} ({psutil.disk_usage('/').percent}%)\n" \
            f"**Public IP:** {subprocess.run(['curl', '--silent', 'ifconfig.me'], capture_output=True).stdout.decode()}\n" \
            f"**Network Usage:** 🔻 {convert_size(psutil.net_io_counters().bytes_recv)} 🔺 {convert_size(psutil.net_io_counters().bytes_sent)}"
    except (AttributeError, KeyError, subprocess.SubprocessError):
        txt = "‼️ Failed to get system info"
    app.edit_message_text(callback_query.from_user.id,
                          callback_query.message.message_id,
                          txt,
                          parse_mode="markdown",
                          reply_markup=button)


@app.on_callback_query(filters=custom_filters.add_category_filter)
def add_category_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"add category: {callback_query.from_user.first_name}")
    db_management.write_support("category_name", callback_query.from_user.id)
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
    try:
        app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id,
                              "Send the category name", reply_markup=button)
    except MessageIdInvalid:
        app.send_message(callback_query.from_user.id, "Send the category name", reply_markup=button)


@app.on_callback_query(filters=custom_filters.ngrok_info_filter)
def ngrok_info_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"/nginfo: {callback_query.from_user.first_name}")
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
    msg = ""
    status_count = 0
    logger.info("fetching ngrok info")
    for url in ngrok_api_url:
        try:
            response = requests.get(url, headers={'Content-Type': 'application/json'})
        except (ConnectionError, HTTPError):
            logger.error(f'failed to connect: {url}')
        else:
            if response.status_code == 200:
                status_count += 1
                tunnels = response.json()["tunnels"]
                for tunnel in tunnels:
                    msg += f'🚀 <b>Name:</b> <code>{tunnel["name"]}</code>\n'
                    msg += f'⚡ <b>URL:</b> {tunnel["public_url"]}\n\n'
            response.close()
    if status_count == len(ngrok_api_url):
        pass
    else:
        msg = '‼️ <b>Failed to get api response</b>'
    app.edit_message_text(callback_query.from_user.id,
                          callback_query.message.message_id,
                          msg,
                          parse_mode="html",
                          reply_markup=button)


@app.on_callback_query(filters=custom_filters.select_category_filter)
def list_categories(client: Client, callback_query: CallbackQuery):
    logger.info(f"list category: {callback_query.from_user.first_name}")
    buttons = []
    try:
        categories = qbittorrent_control.get_categories()
    except Exception:
        logger.error("Error in list_categories")
        txt = "⚠️ Some error occurred"
        app.answer_callback_query(callback_query.id, txt)
    else:
        if categories is None:
            buttons.append([InlineKeyboardButton("🔙 Menu", "menu")])
            app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id,
                                  "There are no categories", reply_markup=InlineKeyboardMarkup(buttons))
            return

        for key, i in enumerate(categories):
            buttons.append([InlineKeyboardButton(i, f"{callback_query.data.split('#')[1]}#{i}")])

        buttons.append([InlineKeyboardButton("🔙 Menu", "menu")])

        try:
            app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id,
                                  "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))
        except MessageIdInvalid:
            app.send_message(callback_query.from_user.id, "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters=custom_filters.remove_category_filter)
def remove_category_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"remove category: {callback_query.from_user.first_name}")
    buttons = [[InlineKeyboardButton("🔙 Menu", "menu")]]
    try:
        qbittorrent_control.remove_category(data=callback_query.data.split("#")[1])
        app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id,
                          f"The category {callback_query.data.split('#')[1]} has been removed",
                          reply_markup=InlineKeyboardMarkup(buttons))
    except Exception:
        logger.error("Error in remove_category_callback")
        txt = "⚠️ Some error occurred"
        app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.modify_category_filter)
def modify_category_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"modify category: {callback_query.from_user.first_name}")
    buttons = [[InlineKeyboardButton("🔙 Menu", "menu")]]

    db_management.write_support(f"category_dir_modify#{callback_query.data.split('#')[1]}", callback_query.from_user.id)
    app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id,
                          f"Send new path for category {callback_query.data.split('#')[1]}",
                          reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters=custom_filters.category_filter)
def category(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"category: {callback_query.from_user.first_name}")
    buttons = []
    try:
        categories = qbittorrent_control.get_categories()
    except Exception:
        logger.error("Error in category")
        txt = "⚠️ Some error occurred"
        app.answer_callback_query(callback_query.id, txt)
    else:
        if categories is None:
            if "magnet" in callback_query.data:
                addmagnet_callback(client, callback_query)

            else:
                addtorrent_callback(client, callback_query)

            return

        for key, i in enumerate(categories):
            buttons.append([InlineKeyboardButton(i, f"{callback_query.data.split('#')[1]}#{i}")])

        buttons.append([InlineKeyboardButton("None", f"{callback_query.data.split('#')[1]}#None")])
        buttons.append([InlineKeyboardButton("🔙 Menu", "menu")])

        try:
            app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id,
                                  "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))
        except MessageIdInvalid:
            app.send_message(callback_query.from_user.id, "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters=custom_filters.menu_filter)
def menu_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"menu: {callback_query.from_user.first_name}")
    send_menu(callback_query.message.message_id, callback_query.from_user.id)


@app.on_callback_query(filters=custom_filters.list_filter)
def list_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"list: {callback_query.from_user.first_name}")
    list_active_torrents(0, callback_query.from_user.id, callback_query.message.message_id,
                         db_management.read_support(callback_query.from_user.id))


@app.on_callback_query(filters=custom_filters.list_by_status_filter)
def list_by_status_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"list by status: {callback_query.from_user.first_name}")
    status_filter = callback_query.data.split("#")[1]
    list_active_torrents(0, callback_query.from_user.id, callback_query.message.message_id,
                         db_management.read_support(callback_query.from_user.id), status_filter=status_filter)


@app.on_callback_query(filters=custom_filters.add_magnet_filter)
def addmagnet_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"add magnet: {callback_query.from_user.first_name}")
    db_management.write_support(f"magnet#{callback_query.data.split('#')[1]}", callback_query.from_user.id)
    app.answer_callback_query(callback_query.id, "Send a magnet link")


@app.on_callback_query(filters=custom_filters.add_torrent_filter)
def addtorrent_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"add torrent: {callback_query.from_user.first_name}")
    db_management.write_support(f"torrent#{callback_query.data.split('#')[1]}", callback_query.from_user.id)
    app.answer_callback_query(callback_query.id, "Send a torrent file")


@app.on_callback_query(filters=custom_filters.pause_all_filter)
def pauseall_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"pause all: {callback_query.from_user.first_name}")
    txt = "⏸️ Paused all torrents"
    try:
        qbittorrent_control.pause_all()
    except Exception:
        logger.error("Error in pauseall_callback")
        txt = "⚠️ Some error occurred"
    app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.resume_all_filter)
def resumeall_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"resume all: {callback_query.from_user.first_name}")
    try:
        msg = "▶️ Resumed all torrents"
        qbittorrent_control.resume_all()
    except Exception:
        logger.error("Error in resumeall_callback")
        msg = "⚠️ Some error occurred"
    app.answer_callback_query(callback_query.id, msg)


@app.on_callback_query(filters=custom_filters.pause_filter)
def pause_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"pause: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.message_id, "pause")

    else:
        try:
            qbittorrent_control.pause(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.message_id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in pause_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.resume_filter)
def resume_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"resume: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.message_id, "resume")

    else:
        try:
            qbittorrent_control.resume(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.message_id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in resume_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_one_filter)
def delete_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.message_id, "delete_one")

    else:

        buttons = [[InlineKeyboardButton("🗑 Delete torrent", f"delete_one_no_data#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🗑 Delete torrent and data", f"delete_one_data#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🔙 Menu", "menu")]]

        try:
            app.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id,
                                      reply_markup=InlineKeyboardMarkup(buttons))
        except (MessageIdInvalid, MessageNotModified):
            logger.error("Error in delete_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_one_no_data_filter)
def delete_no_data_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete no data: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.message_id, "delete_one_no_data")

    else:
        try:
            qbittorrent_control.delete_one_no_data(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.message_id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in delete_no_data_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_one_data_filter)
def delete_with_data_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete with data: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.message_id, "delete_one_data")

    else:
        try:
            qbittorrent_control.delete_one_data(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.message_id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in delete_with_data_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_all_filter)
def delete_all_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete all: {callback_query.from_user.first_name}")
    buttons = [[InlineKeyboardButton("🗑 Delete all torrents", "delete_all_no_data")],
               [InlineKeyboardButton("🗑 Delete all torrents and data", "delete_all_data")],
               [InlineKeyboardButton("🔙 Menu", "menu")]]
    try:
        app.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.message_id,
                                  reply_markup=InlineKeyboardMarkup(buttons))
    except (MessageIdInvalid, MessageNotModified):
        logger.error("Error in delete_all_callback")
        txt = "⚠️ Some error occurred"
        app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_all_no_data_filter)
def delete_all_with_no_data_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete all no data: {callback_query.from_user.first_name}")
    txt = "🗑 Deleted only torrents"
    try:
        qbittorrent_control.delall_no_data()
    except Exception:
        logger.error("Error in delete_all_with_no_data_callback")
        txt = "⚠️ Some error occurred"
    app.answer_callback_query(callback_query.id, txt)
    send_menu(callback_query.message.message_id, callback_query.from_user.id)


@app.on_callback_query(filters=custom_filters.delete_all_data_filter)
def delete_all_with_data_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete all with data: {callback_query.from_user.first_name}")
    txt = "🗑 Deleted All Torrents+Data"
    try:
        qbittorrent_control.delall_data()
    except Exception:
        logger.error("Error in delete_all_with_data_callback")
        txt = "⚠️ Some error occurred"
    app.answer_callback_query(callback_query.id, txt)
    send_menu(callback_query.message.message_id, callback_query.from_user.id)


@app.on_callback_query(filters=custom_filters.torrentInfo_filter)
def torrent_info_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"torrent info: {callback_query.from_user.first_name}")
    try:
        torrent = qbittorrent_control.get_torrent_info(data=int(callback_query.data.split("#")[1]))
    except Exception:
        logger.error("Error in torrent_info_callback")
        txt = "⚠️ Some error occurred"
        app.answer_callback_query(callback_query.id, txt)
    else:
        progress = torrent.progress * 100
        text = ""

        if progress == 0:
            text += f"{torrent.name}\n[            ] " \
                    f"{round(progress, 2)}% completed\n" \
                    f"State: {torrent.state.capitalize()}\n" \
                    f"Download Speed: {convert_size(torrent.dlspeed)}/s\n" \
                    f"Size: {convert_size(torrent.size)}\nETA: " \
                    f"{convert_eta(int(torrent.eta))}\n" \
                    f"Category: {torrent.category}\n"

        elif progress == 100:
            text += f"{torrent.name}\n[completed] " \
                    f"{round(progress, 2)}% completed\n" \
                    f"State: {torrent.state.capitalize()}\n" \
                    f"Upload Speed: {convert_size(torrent.upspeed)}/s\n" \
                    f"Category: {torrent.category}\n"

        else:
            text += f"{torrent.name}\n[{'=' * int(progress / 10)}" \
                    f"{' ' * int(12 - (progress / 10))}]" \
                    f" {round(progress, 2)}% completed\n" \
                    f"State: {torrent.state.capitalize()} \n" \
                    f"Download Speed: {convert_size(torrent.dlspeed)}/s\n" \
                    f"Size: {convert_size(torrent.size)}\nETA: " \
                    f"{convert_eta(int(torrent.eta))}\n" \
                    f"Category: {torrent.category}\n"

        buttons = [[InlineKeyboardButton("⏸ Pause", f"pause#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("▶️ Resume", f"resume#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🗑 Delete", f"delete_one#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🔙 Menu", "menu")]]

        app.edit_message_text(callback_query.from_user.id, callback_query.message.message_id, text=text,
                              reply_markup=InlineKeyboardMarkup(buttons))


@app.on_message()
def on_text(client: Client, message: Message) -> None:
    logger.info(f"on text: {message.from_user.first_name}")
    action = db_management.read_support(message.from_user.id)

    if "magnet" in action:
        if message.text.startswith("magnet:?xt"):
            magnet_link = message.text.split("\n")
            category = db_management.read_support(message.from_user.id).split("#")[1]
            qbittorrent_control.add_magnet(magnet_link=magnet_link,
                                           category=category)
            send_menu(message.message_id, message.from_user.id)
            db_management.write_support("None", message.from_user.id)

        else:
            message.reply_text("This magnet link is invalid! Retry")

    elif "torrent" in action and message.document:
        if ".torrent" in message.document.file_name:
            with tempfile.TemporaryDirectory() as tempdir:
                name = f"{tempdir}/{message.document.file_name}"
                category = db_management.read_support(message.from_user.id).split("#")[1]
                message.download(name)
                qbittorrent_control.add_torrent(file_name=name,
                                                category=category)
            send_menu(message.message_id, message.from_user.id)
            db_management.write_support("None", message.from_user.id)

        else:
            message.reply_text("This is not a torrent file! Retry")

    elif action == "category_name":
        db_management.write_support(f"category_dir#{message.text}", message.from_user.id)
        message.reply_text(f"now send me the path for the category {message.text}")

    elif "category_dir" in action:
        if os.path.exists(message.text):
            name = db_management.read_support(message.from_user.id).split("#")[1]

            if "modify" in action:
                qbittorrent_control.edit_category(name=name,
                                                  save_path=message.text)
                send_menu(message.message_id, message.from_user.id)
                return

            qbittorrent_control.create_category(name=name,
                                                save_path=message.text)
            send_menu(message.message_id, message.from_user.id)

        else:
            message.reply_text("The path entered does not exist! Retry")
