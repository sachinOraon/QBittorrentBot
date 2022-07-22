from os import getenv

# Qbittorrent settings
QBITTORRENT_IP = getenv("qbIp")
QBITTORRENT_PORT = getenv("qbPort")
QBITTORRENT_USER = getenv("qbUser")
QBITTORRENT_PSW = getenv("qbPsw")

# Bot access
TG_TOKEN = getenv("TG-KEY")
API_ID = getenv("API-ID")
API_HASH = getenv("API-HASH")

# Bot settings
NOTIFY = False
AUTHORIZED_IDS = []

# Aria settings
ARIA_IP = getenv("ARIA_IP")
ARIA_PORT = getenv("ARIA_PORT")
ARIA_RPC_TOKEN = getenv("ARIA_RPC_TOKEN")
ARIA_DOWNLOAD_PATH = "/mnt/downloads"
