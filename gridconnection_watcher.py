import sys
import os
import logging
import time
from module_m_decoder import ModuleM


logging.info("starting gridconnection_watcher.py")

module_m = ModuleM()

def update():
    if module_m._read_data() and module_m._decode_data():
        pass


def update_from_github():
    logging.info("updating gridconnection_watcher.py")
    os.system("sudo git pull")
    os.system("sudo systemctl restart gridconnection_watcher.service")



if __name__ == "__main__":
    time.sleep(5) # sleep 5 seconds at startup. If we crash, we overload systemD with too many restarts when not sleeping
    # Configure logging to send messages to stdout (captured by systemd)
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    
    while True:
        update()
        time.sleep(0.3)