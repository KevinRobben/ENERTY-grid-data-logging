import sys
import os
import _thread as thread


import logging
import time

# Configure logging to send messages to stdout (captured by systemd)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

logging.info("starting gridconnection_watcher.py")

time.sleep(5)

raise ValueError("Grid connection not found")