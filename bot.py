import datetime
import os
import time
import tempfile
import pyrogram.errors.exceptions.bad_request_400
import requests
import subprocess
from math import log, floor, ceil
from requests import ConnectionError
from requests import HTTPError
from pyrogram import Client, filters, enums
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery
from pyrogram.errors.exceptions import MessageIdInvalid
from pyrogram.errors.exceptions.bad_request_400 import PeerIdInvalid, MessageNotModified
from logging2 import Logger
import psutil
import custom_filters
import qbittorrent_control
from config import API_ID, API_HASH, TG_TOKEN, AUTHORIZED_IDS, ARIA_IP, ARIA_PORT, ARIA_RPC_TOKEN, ARIA_DOWNLOAD_PATH
import db_management
import aria2p
import docker
from aria2p import API

logger = Logger(__name__)
app = Client("qbittorrent_bot", api_id=API_ID, api_hash=API_HASH, bot_token=TG_TOKEN)
ngrok_api_url = ["http://127.0.0.1:4040/api/tunnels", "http://127.0.0.1:4050/api/tunnels"]
aria = None
if ARIA_IP is None or ARIA_PORT is None:
    logger.error("aria is not configured")
else:
    try:
        aria = aria2p.API(
            aria2p.Client(
                host=f"http://{ARIA_IP}",
                port=ARIA_PORT,
                secret=ARIA_RPC_TOKEN
            )
        )
        dclient = docker.DockerClient(base_url=f"unix://var/run/docker.sock")

        def aria_onDownloadComplete(api: API, gid: str = None):
            logger.info("aria download complete event triggered")
            if gid is None:
                logger.error("aria gid is None")
            else:
                logger.info(f"fetching aria info for: {gid}")
                down = aria.get_download(gid)
                name = down.name
                for uid in AUTHORIZED_IDS:
                    try:
                        app.send_message(chat_id=uid, text=f"🗂 <code>{name}</code> <b>downloaded</b> ✔️", parse_mode=enums.ParseMode.HTML)
                    except Exception:
                        logger.error(f"failed to send notification to {uid}")
                logger.info(f"starting file extraction for {name}")
                try:
                    dclient.containers.run(image="amarcu5/7zip", command=f"x '{name}'", remove=True, detach=False,
                                           volumes={os.getenv("DOWNLOAD_PATH"): {'bind': ARIA_DOWNLOAD_PATH, 'mode': 'rw'}},
                                           working_dir=ARIA_DOWNLOAD_PATH)
                except docker.errors.ContainerError as err_msg:
                    logger.error(f"failed to extract {name}: {str(err_msg)}")
                except (docker.errors.APIError, docker.errors.ImageNotFound):
                    logger.error("failed to initialize 7zip container")
                else:
                    logger.info(f"extraction completed, removing {name}")
                    try:
                        os.remove(path=f"{ARIA_DOWNLOAD_PATH}/{name}")
                        aria.remove(downloads=[down], files=False, clean=True, force=True)
                        for uid in AUTHORIZED_IDS:
                            app.send_message(chat_id=uid, text=f"🗂 <code>{name}</code> <b>extracted</b> ✔️", parse_mode=enums.ParseMode.HTML)
                    except Exception as e:
                        logger.error(f"error in download complete event: {str(e)}")

        aria.listen_to_notifications(threaded=True, on_download_complete=aria_onDownloadComplete)
    except Exception as err:
        logger.error(f"Failed to initialize aria/docker: {str(err)}")


def get_ngrok_info():
    max_retry = 5
    retry_count = 0
    sleep_sec = 10
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
        if status_count > 0:
            break
    if retry_count > max_retry:
        logger.error("failed to get ngrok info on startup")
    else:
        for user_id in AUTHORIZED_IDS:
            try:
                app.send_message(user_id, msg, parse_mode=enums.ParseMode.HTML)
            except (PeerIdInvalid, ConnectionError):
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
               [InlineKeyboardButton("🧬 Download & Extract", "extract_file"),
                InlineKeyboardButton("🚀 Ngrok Info", "ngrok_info")]]

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
        app.edit_message_text(chat, message, txt, parse_mode=enums.ParseMode.HTML, reply_markup=button)
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
        send_menu(message.id, message.chat.id)

    else:
        button = InlineKeyboardMarkup([[InlineKeyboardButton("Github",
                                                             url="https://github.com/ch3p4ll3/QBittorrentBot/")]])
        app.send_message(message.chat.id, "You are not authorized to use this bot", reply_markup=button)


@app.on_callback_query(filters=custom_filters.system_info_filter)
def stats_command(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"/stats: {callback_query.from_user.first_name}")
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
    try:
        temp = psutil.sensors_temperatures()
        cpu_temp = ""
        if len(temp) != 0:
            if "coretemp" in temp:
                key = "coretemp"
            elif "cpu_thermal" in temp:
                key = "cpu_thermal"
            else:
                key = None
            if key:
                for t in temp[key]:
                    cpu_temp += f"{t.current}°C  "
        else:
            cpu_temp += "NA"
        ip_cmd = "hostname -I | cut -d\' \' -f1"
        txt = f"**============SYSTEM============**\n" \
            f"**CPU Usage:** {psutil.cpu_percent(interval=None)}%\n" \
            f"**CPU Freq:** {ceil(psutil.cpu_freq(percpu=False).current)} MHz\n" \
            f"**CPU Cores:** {psutil.cpu_count(logical=True)}\n" \
            f"**CPU Temp:** {cpu_temp}\n" \
            f"**Free Memory:** {convert_size(psutil.virtual_memory().available)} of " \
            f"{convert_size(psutil.virtual_memory().total)}\n" \
            f"**Used Memory:** {convert_size(psutil.virtual_memory().used)} ({psutil.virtual_memory().percent}%)\n" \
            f"**Disks usage:** {convert_size(psutil.disk_usage('/').used)} of " \
            f"{convert_size(psutil.disk_usage('/').total)} ({psutil.disk_usage('/').percent}%)\n" \
            f"**Local IP:** {subprocess.check_output(ip_cmd, shell=True).decode()}" \
            f"**Public IP:** {subprocess.run(['curl', '--silent', 'ifconfig.me'], capture_output=True).stdout.decode()}\n" \
            f"**Network Usage:** 🔻 {convert_size(psutil.net_io_counters().bytes_recv)} 🔺 {convert_size(psutil.net_io_counters().bytes_sent)}\n" \
            f"**Uptime:** {subprocess.check_output('uptime --pretty', shell=True).decode()}"
    except (AttributeError, KeyError, subprocess.SubprocessError, subprocess.CalledProcessError) as e:
        txt = f"‼️ Failed to get system info: {str(e)}"
    app.edit_message_text(callback_query.from_user.id,
                          callback_query.message.id,
                          txt,
                          parse_mode=enums.ParseMode.MARKDOWN,
                          reply_markup=button)


@app.on_callback_query(filters=custom_filters.add_category_filter)
def add_category_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"add category: {callback_query.from_user.first_name}")
    db_management.write_support("category_name", callback_query.from_user.id)
    button = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", "menu")]])
    try:
        app.edit_message_text(callback_query.from_user.id, callback_query.message.id,
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
    if status_count == 0:
        msg = '‼️ <b>Failed to get api response</b>'
    app.edit_message_text(callback_query.from_user.id,
                          callback_query.message.id,
                          msg,
                          parse_mode=enums.ParseMode.HTML,
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
            app.edit_message_text(callback_query.from_user.id, callback_query.message.id,
                                  "There are no categories", reply_markup=InlineKeyboardMarkup(buttons))
            return

        for key, i in enumerate(categories):
            buttons.append([InlineKeyboardButton(i, f"{callback_query.data.split('#')[1]}#{i}")])

        buttons.append([InlineKeyboardButton("🔙 Menu", "menu")])

        try:
            app.edit_message_text(callback_query.from_user.id, callback_query.message.id,
                                  "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))
        except MessageIdInvalid:
            app.send_message(callback_query.from_user.id, "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters=custom_filters.remove_category_filter)
def remove_category_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"remove category: {callback_query.from_user.first_name}")
    buttons = [[InlineKeyboardButton("🔙 Menu", "menu")]]
    try:
        qbittorrent_control.remove_category(data=callback_query.data.split("#")[1])
        app.edit_message_text(callback_query.from_user.id, callback_query.message.id,
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
    app.edit_message_text(callback_query.from_user.id, callback_query.message.id,
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
            app.edit_message_text(callback_query.from_user.id, callback_query.message.id,
                                  "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))
        except MessageIdInvalid:
            app.send_message(callback_query.from_user.id, "Choose a category:", reply_markup=InlineKeyboardMarkup(buttons))


@app.on_callback_query(filters=custom_filters.menu_filter)
def menu_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"menu: {callback_query.from_user.first_name}")
    send_menu(callback_query.message.id, callback_query.from_user.id)


@app.on_callback_query(filters=custom_filters.list_filter)
def list_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"list: {callback_query.from_user.first_name}")
    list_active_torrents(0, callback_query.from_user.id, callback_query.message.id,
                         db_management.read_support(callback_query.from_user.id))


@app.on_callback_query(filters=custom_filters.list_by_status_filter)
def list_by_status_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"list by status: {callback_query.from_user.first_name}")
    status_filter = callback_query.data.split("#")[1]
    list_active_torrents(0, callback_query.from_user.id, callback_query.message.id,
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
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.id, "pause")

    else:
        try:
            qbittorrent_control.pause(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in pause_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.resume_filter)
def resume_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"resume: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.id, "resume")

    else:
        try:
            qbittorrent_control.resume(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in resume_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_one_filter)
def delete_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.id, "delete_one")

    else:

        buttons = [[InlineKeyboardButton("🗑 Delete torrent", f"delete_one_no_data#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🗑 Delete torrent and data", f"delete_one_data#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🔙 Menu", "menu")]]

        try:
            app.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.id,
                                      reply_markup=InlineKeyboardMarkup(buttons))
        except (MessageIdInvalid, MessageNotModified):
            logger.error("Error in delete_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_one_no_data_filter)
def delete_no_data_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete no data: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.id, "delete_one_no_data")

    else:
        try:
            qbittorrent_control.delete_one_no_data(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.id, callback_query.from_user.id)
        except Exception:
            logger.error("Error in delete_no_data_callback")
            txt = "⚠️ Some error occurred"
            app.answer_callback_query(callback_query.id, txt)


@app.on_callback_query(filters=custom_filters.delete_one_data_filter)
def delete_with_data_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"delete with data: {callback_query.from_user.first_name}")
    if callback_query.data.find("#") == -1:
        list_active_torrents(1, callback_query.from_user.id, callback_query.message.id, "delete_one_data")

    else:
        try:
            qbittorrent_control.delete_one_data(id_torrent=int(callback_query.data.split("#")[1]))
            send_menu(callback_query.message.id, callback_query.from_user.id)
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
        app.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.id,
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
    send_menu(callback_query.message.id, callback_query.from_user.id)


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
    send_menu(callback_query.message.id, callback_query.from_user.id)


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
            text += f"🗂 {torrent.name}\n⌈□□□□□□□□□□□□⌋ " \
                    f"{round(progress, 2)}% completed\n" \
                    f"🚦 State: {torrent.state.capitalize()}\n" \
                    f"⚡ Download Speed: {convert_size(torrent.dlspeed)}/s\n" \
                    f"📀 Size: {convert_size(torrent.size)}\n⏳ ETA: " \
                    f"{convert_eta(int(torrent.eta))}\n" \
                    f"🧲 Category: {torrent.category}\n"

        elif progress == 100:
            text += f"🗂 {torrent.name}\n⌈completed⌋ " \
                    f"{round(progress, 2)}% completed\n" \
                    f"🚦 State: {torrent.state.capitalize()}\n" \
                    f"📤 Upload Speed: {convert_size(torrent.upspeed)}/s\n" \
                    f"🧲 Category: {torrent.category}\n"

        else:
            text += f"🗂 {torrent.name}\n⌈{'■' * int(progress / 10)}" \
                    f"{'□' * int(12 - (progress / 10))}⌋" \
                    f" {round(progress, 2)}% completed\n" \
                    f"🚦 State: {torrent.state.capitalize()} \n" \
                    f"⚡ Download Speed: {convert_size(torrent.dlspeed)}/s\n" \
                    f"📀 Size: {convert_size(torrent.size)}\n⏳ ETA: " \
                    f"{convert_eta(int(torrent.eta))}\n" \
                    f"🧲 Category: {torrent.category}\n"

        buttons = [[InlineKeyboardButton("⏸ Pause", f"pause#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("▶️ Resume", f"resume#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🗑 Delete", f"delete_one#{callback_query.data.split('#')[1]}")],
                   [InlineKeyboardButton("🔙 Menu", "menu")]]

        app.edit_message_text(callback_query.from_user.id, callback_query.message.id, text=text,
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
            send_menu(message.id, message.from_user.id)
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
            send_menu(message.id, message.from_user.id)
            db_management.write_support("None", message.from_user.id)

        else:
            message.reply_text("This is not a torrent file! Retry")

    elif "extract" in action:
        if message.text.startswith("http"):
            logger.info(f"checking url: {message.text}")
            try:
                resp = requests.get(url=message.text, headers={"range": "bytes=0-512"})
                if resp.ok:
                    logger.info("starting download using aria")
                    aria_download = aria.add_uris(uris=[message.text])
                    if aria_download.error_code:
                        message.reply_text(f"❗ Error while starting download: {aria_download.error_message} ⚠")
                    else:
                        logger.info(f"download started: GID: {aria_download.gid}")
                        needed = aria.get_download(aria_download.gid).total_length * 2
                        avail = psutil.disk_usage(ARIA_DOWNLOAD_PATH).free
                        if avail < needed:
                            logger.error("stopping download due to less space")
                            for rem in aria.remove(downloads=[aria.get_download(aria_download.gid)], files=True, clean=True):
                                logger.info(f"GID: {aria_download.gid} [{rem.message} {rem.code}]")
                            message.reply_text(f"⚠ <b>Download stopped due to lack of space</b> ❌\n\n🗂 Filename: <code>{aria.get_download(aria_download.gid).name}</code>\n\n📀 Size: {convert_size(aria.get_download(aria_download.gid).total_length)}\n\n💾 Expected: {convert_size(needed)}\n📦 Available: {convert_size(avail)}", parse_mode=enums.ParseMode.HTML)
                        else:
                            msg = f"🗂 Filename: <code>{aria_download.name}</code>\n\n🚦 Status: {aria_download.status}\n\n📀 Size: {aria_download.total_length_string()}\n" \
                                  f"📥 Downloaded: {aria_download.completed_length_string()} ({aria_download.progress_string()})\n\n" \
                                  f"⚡ Speed: {aria_download.download_speed_string()}\n⏰ ETA: {aria_download.eta_string()}"
                            buttons = [[InlineKeyboardButton("♻ Refresh", f"aria-ref#{aria_download.gid}"),
                                        InlineKeyboardButton("❌ Cancel", f"aria-can#{aria_download.gid}")],
                                       [InlineKeyboardButton("⏸ Pause", f"aria-pau#{aria_download.gid}"),
                                        InlineKeyboardButton("🔙 Menu", "menu")]]
                            message.reply_text(text=msg, parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
                            db_management.write_support("None", message.from_user.id)
                else:
                    message.reply_text(f"⚠ Error connecting to given link or invalid file:{resp.reason}:{resp.status_code} ⁉")
            except (ConnectionError, HTTPError):
                logger.error(f"failed to validate url: {message.text}")
                message.reply_text(f"Unable to validate the given link ❗")
            except aria2p.client.ClientException as exp:
                logger.error(f"error occurred in aria instance: {str(exp)}")
                message.reply_text("Something went wrong with Aria ⁉")
            else:
                resp.close()
        else:
            message.reply_text("Invalid download link given ‼")

    elif action == "category_name":
        db_management.write_support(f"category_dir#{message.text}", message.from_user.id)
        message.reply_text(f"now send me the path for the category {message.text}")

    elif "category_dir" in action:
        if os.path.exists(message.text):
            name = db_management.read_support(message.from_user.id).split("#")[1]

            if "modify" in action:
                qbittorrent_control.edit_category(name=name,
                                                  save_path=message.text)
                send_menu(message.id, message.from_user.id)
                return

            qbittorrent_control.create_category(name=name,
                                                save_path=message.text)
            send_menu(message.id, message.from_user.id)

        else:
            message.reply_text("The path entered does not exist! Retry")


@app.on_callback_query(filters=custom_filters.extract_file_filter)
def extract_file_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"extract file cmd sent by: {callback_query.from_user.first_name}")
    if aria is None:
        app.answer_callback_query(callback_query.id, "Aria is not configured properly ‼")
    else:
        logger.info("fetching the aria downloads")
        try:
            if len(aria.get_downloads()) > 0:
                file_btns = []
                for down in aria.get_downloads():
                    btn = [InlineKeyboardButton(f"{down.name}", f"aria-ref#{down.gid}")]
                    file_btns.append(btn)
                file_btns.append([InlineKeyboardButton("➕ Add", "aria-add"), InlineKeyboardButton("🔙 Menu", "menu")])
                app.edit_message_reply_markup(callback_query.from_user.id, callback_query.message.id,
                                              InlineKeyboardMarkup(file_btns))
            else:
                logger.info("no aria downloads found")
                app.answer_callback_query(callback_query.id, "Send a download link 🔗")
                db_management.write_support(f"{callback_query.data}", callback_query.from_user.id)
        except Exception as e:
            logger.error(f"failed to process cmd: {str(e)}")
            app.answer_callback_query(callback_query.id, "⚠ Some error occurred ❗")


@app.on_callback_query(filters=custom_filters.aria_ref_filter)
def aria_ref_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"aria download refresh cmd by: {callback_query.from_user.first_name}")
    try:
        aria_gid = callback_query.data.split('#')[1]
        logger.info(f"getting aria download info for: {aria_gid}")
        down = aria.get_download(aria_gid)
        msg = f"🗂 Filename: <code>{down.name}</code>\n\n🚦 Status: {down.status}\n\n📀 Size: {down.total_length_string()}\n"\
            f"📥 Downloaded: {down.completed_length_string()} ({down.progress_string()})\n\n"\
            f"⚡ Speed: {down.download_speed_string()}\n⏰ ETA: {down.eta_string()}"
        if "error" in down.status:
            other_btn = [InlineKeyboardButton("🚀 Retry", f"aria-ret#{aria_gid}"), InlineKeyboardButton("🔙 Menu", "menu")]
        elif "paused" in down.status:
            other_btn = [InlineKeyboardButton("▶ Resume", f"aria-res#{aria_gid}"), InlineKeyboardButton("🔙 Menu", "menu")]
        elif "active" in down.status:
            other_btn = [InlineKeyboardButton("⏸ Pause", f"aria-pau#{aria_gid}"), InlineKeyboardButton("🔙 Menu", "menu")]
        else:
            other_btn = [InlineKeyboardButton("🔙 Menu", "menu")]
        buttons = [[InlineKeyboardButton("♻ Refresh", f"aria-ref#{aria_gid}"),
                    InlineKeyboardButton("❌ Cancel", f"aria-can#{aria_gid}")], other_btn]
        app.edit_message_text(callback_query.from_user.id, callback_query.message.id, text=msg,
                              parse_mode=enums.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(buttons))
        logger.info(f"download info sent to: {callback_query.from_user.first_name}")
    except pyrogram.errors.exceptions.bad_request_400.MessageNotModified:
        pass
    except Exception as e:
        logger.error(f"failed to process refresh cmd: {str(e)}")
        app.answer_callback_query(callback_query.id, "⚠ Failed to refresh")


@app.on_callback_query(filters=custom_filters.aria_can_filter)
def aria_can_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"aria download cancel cmd sent by: {callback_query.from_user.first_name}")
    try:
        aria_gid = callback_query.data.split('#')[1]
        logger.info(f"getting aria download info for: {aria_gid}")
        filename = aria.get_download(aria_gid).name
        remove = aria.remove(downloads=[aria.get_download(aria_gid)], force=True, files=True, clean=True)
        logger.info(f"download cancelled for: {filename}")
        app.answer_callback_query(callback_query.id, f"❌ Download cancelled for: {filename}")
        send_menu(callback_query.message.id, callback_query.from_user.id)
    except Exception as e:
        logger.error(f"failed to process cancel cmd: {str(e)}")
        app.answer_callback_query(callback_query.id, "⚠ Failed to cancel downloading")


@app.on_callback_query(filters=custom_filters.aria_add_filter)
def aria_add_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"aria download add cmd sent by: {callback_query.from_user.first_name}")
    app.answer_callback_query(callback_query.id, "Send a download link 🔗")
    db_management.write_support("extract", callback_query.from_user.id)


@app.on_callback_query(filters=custom_filters.aria_ret_filter)
def aria_ret_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"aria retry cmd sent by: {callback_query.from_user.first_name}")
    try:
        aria_gid = callback_query.data.split('#')[1]
        filename = aria.get_download(aria_gid).name
        logger.info(f"retrying download: {filename}")
        aria.retry_downloads(downloads=[aria.get_download(aria_gid)], clean=False)
        app.answer_callback_query(callback_query.id, f"⚡ Retry download: {filename}")
        send_menu(callback_query.message.id, callback_query.from_user.id)
    except Exception as e:
        logger.error(f"failed to retry download: {str(e)}")
        app.answer_callback_query(callback_query.id, f"❗ Unable to retry download")


@app.on_callback_query(filters=custom_filters.aria_pau_filter)
def aria_pau_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"aria pause cmd sent by: {callback_query.from_user.first_name}")
    try:
        aria_gid = callback_query.data.split('#')[1]
        filename = aria.get_download(aria_gid).name
        logger.info(f"pausing download: {filename}")
        aria.pause(downloads=[aria.get_download(aria_gid)], force=True)
        app.answer_callback_query(callback_query.id, f"⏸ Paused: {filename}")
        send_menu(callback_query.message.id, callback_query.from_user.id)
    except Exception as e:
        logger.error(f"failed to pause download: {str(e)}")
        app.answer_callback_query(callback_query.id, f"❗ Unable to pause download")


@app.on_callback_query(filters=custom_filters.aria_res_filter)
def aria_res_callback(client: Client, callback_query: CallbackQuery) -> None:
    logger.info(f"aria resume cmd sent by: {callback_query.from_user.first_name}")
    try:
        aria_gid = callback_query.data.split('#')[1]
        filename = aria.get_download(aria_gid).name
        logger.info(f"resuming download: {filename}")
        aria.resume(downloads=[aria.get_download(aria_gid)])
        app.answer_callback_query(callback_query.id, f"▶ Resumed: {filename}")
        send_menu(callback_query.message.id, callback_query.from_user.id)
    except Exception as e:
        logger.error(f"failed to resume download: {str(e)}")
        app.answer_callback_query(callback_query.id, f"❗ Unable to resume download")
