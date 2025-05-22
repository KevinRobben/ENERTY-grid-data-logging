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
BOOT_COMMAND_TIMEOUT = 5  # seconds to wait for response
BOOT_COMMAND_RETRY_DELAY = 3  # seconds to wait before retrying
MAX_BOOT_RETRIES = 5  # maximum number of retries for boot command


def find_serial_port():
    ports = glob.glob('/dev/ttyACM*')
    if not ports:
        print("[!] No /dev/ttyACM* devices found.")
        sys.exit(1)
    return ports[0]

def send_boot_command(serial_port):
    """Send boot command and verify response with retry logic"""
    for attempt in range(MAX_BOOT_RETRIES):
        try:
            with serial.Serial(serial_port, BAUDRATE, timeout=BOOT_COMMAND_TIMEOUT) as ser:
                # Clear any existing data in the buffer
                ser.reset_input_buffer()
                
                print(f"[*] Attempt {attempt + 1}/{MAX_BOOT_RETRIES}: Sending '$D' to ESP32...")
                ser.write(b'$D')
                ser.flush()  # Ensure data is sent immediately
                
                # Read response with timeout
                start_time = time.time()
                response_buffer = b''
                
                while time.time() - start_time < BOOT_COMMAND_TIMEOUT:
                    if ser.in_waiting > 0:
                        chunk = ser.read(ser.in_waiting)
                        response_buffer += chunk
                        
                        # Convert to string for checking
                        response_str = response_buffer.decode('utf-8', errors='ignore')
                        print(f"[*] Received: {response_str.strip()}")
                        
                        # Check if we got the expected response
                        if "Triggering bootloader" in response_str:
                            print("[+] Bootloader trigger confirmed!")
                            return True
                    
                    time.sleep(0.1)  # Small delay to avoid busy waiting
                
                # If we get here, we didn't receive the expected response
                response_str = response_buffer.decode('utf-8', errors='ignore')
                if response_str.strip():
                    print(f"[!] Unexpected response: {response_str.strip()}")
                else:
                    print("[!] No response received from ESP32")
                
        except serial.SerialException as e:
            print(f"[!] Serial error on attempt {attempt + 1}: {e}")
        
        # Wait before retrying (except on the last attempt)
        if attempt < MAX_BOOT_RETRIES - 1:
            print(f"[*] Waiting {BOOT_COMMAND_RETRY_DELAY} seconds before retry...")
            time.sleep(BOOT_COMMAND_RETRY_DELAY)
    
    # If we get here, all attempts failed
    print(f"[!] Failed to trigger bootloader after {MAX_BOOT_RETRIES} attempts")
    return False

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

    # Send boot command with response verification
    if not send_boot_command(serial_port):
        print("[!] Failed to trigger bootloader. Exiting.")
        exit(1)

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