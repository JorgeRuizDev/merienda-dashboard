import subprocess
import sys
import time

import requests
import webview


def main():
    process = subprocess.Popen([sys.executable, "-m", "reflex", "run", "--env", "dev"])

    for attempt in range(10):
        try:
            requests.get("http://localhost:3000")
            break
        except requests.exceptions.ConnectionError:
            time.sleep(10)
        if attempt == 9:
            raise Exception("Failed to connect to server")

    webview.create_window("Merienda", "http://localhost:3000", fullscreen=True)
    webview.start()
    process.terminate()


if __name__ == "__main__":
    main()
