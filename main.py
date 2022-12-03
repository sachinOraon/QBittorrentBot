from bot import app, get_ngrok_info
import threading

if __name__ == '__main__':
    threading.Thread(target=get_ngrok_info).start()
    app.run()
