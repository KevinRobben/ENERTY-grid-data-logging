#!/usr/bin/env python3
import os
import time
import subprocess
import argparse
import serial
import requests
import glob
import sys
import yaml



BAUDRATE = 115200
UF2_TIMEOUT = 60  # seconds
MOUNT_BASE = "/media/esp32"


def find_serial_port():
    ports = glob.glob('/dev/ttyACM*')
    if not ports:
        print("[!] No /dev/ttyACM* devices found.")
        sys.exit(1)
    return ports[0]

def send_boot_command(serial_port):
    try:
        with serial.Serial(serial_port, BAUDRATE, timeout=1) as ser:
            print("[*] Sending '$D' to ESP32...")
            ser.write(b'$D')
            time.sleep(1)
    except serial.SerialException as e:
        print(f"[!] Serial error: {e}")
        exit(1)

def wait_for_usb_drive():
    print("[*] Waiting for ESP32 USB drive to appear...")
    start_time = time.time()
    while time.time() - start_time < UF2_TIMEOUT:
        drives = subprocess.getoutput("lsblk -o NAME,MOUNTPOINT | grep /media/").splitlines()
        for line in drives:
            if "/media/" in line:
                parts = line.strip().split()
                if len(parts) > 1:
                    return parts[1]
        time.sleep(1)
    return None

def download_firmware(github_url, token, output_file="firmware.uf2"):
    print(f"[*] Downloading firmware from GitHub...")
    headers = {'Authorization': f'token {token}'}
    r = requests.get(github_url, headers=headers, stream=True)
    if r.status_code == 200:
        with open(output_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print("[+] Firmware downloaded.")
    else:
        print(f"[!] Failed to download firmware: {r.status_code}")
        exit(1)

def copy_firmware_to_drive(uf2_path, mount_point):
    dest_path = os.path.join(mount_point, os.path.basename(uf2_path))
    print(f"[*] Copying firmware to {dest_path}...")
    subprocess.run(["cp", uf2_path, dest_path])
    print("[+] Firmware copied.")

def wait_for_drive_to_disappear(mount_point):
    print("[*] Waiting for ESP32 to reboot and drive to disappear...")
    start_time = time.time()
    while time.time() - start_time < UF2_TIMEOUT:
        if not os.path.ismount(mount_point):
            print("[+] Drive disappeared. Update likely successful.")
            return True
        time.sleep(1)
    print("[!] Drive did not disappear in time.")
    return False


def load_github_token(path='user_data.yaml'):
    try:
        with open(path, 'r') as f:
            data = yaml.safe_load(f)
            token = data.get('github_token')
            if not token:
                print("[!] Token not found in YAML file.")
                exit(1)
            return token
    except FileNotFoundError:
        print(f"[!] Token file {path} not found.")
        exit(1)

def convert_to_raw_url(github_url):
    if "github.com" in github_url and "/blob/" in github_url:
        return github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return github_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("github_url", help="Direct link to UF2 file in private GitHub repo")
    args = parser.parse_args()

    github_url = convert_to_raw_url(args.github_url)

    github_token = load_github_token()

    download_firmware(github_url, github_token)

    serial_port = find_serial_port()
    print(f"[*] Found serial port: {serial_port}")

    send_boot_command(serial_port)

    mount_point = wait_for_usb_drive()
    if not mount_point:
        print("[!] USB drive not detected. Exiting.")
        exit(1)

    copy_firmware_to_drive("firmware.uf2", mount_point)

    if not wait_for_drive_to_disappear(mount_point):
        print("[!] Rebooting Raspberry Pi as fallback...")
        subprocess.run(["sudo", "reboot"])

if __name__ == "__main__":
    main()
