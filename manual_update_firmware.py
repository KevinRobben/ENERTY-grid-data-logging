#!/usr/bin/env python3
import os
import time
import subprocess
import argparse
import serial
import requests
import glob


BAUDRATE = 9600
UF2_TIMEOUT = 20  # seconds
UF2_FLASH_RETRIES = 3  # number of times to retry firmware upload
MOUNT_BASE = "/tmp/esp32_mount"
BOOT_COMMAND_TIMEOUT = 5  # seconds to wait for response
BOOT_COMMAND_RETRY_DELAY = 3  # seconds to wait before retrying
MAX_BOOT_RETRIES = 5  # maximum number of retries for boot command
MAX_FIRMWARE_RETRIES = 3  # maximum number of retries for firmware version check
WINDOWS = os.name == 'nt'

def find_serial_port(indent=""):
    """Find the first available /dev/ttyACM port."""
    ports = glob.glob('/dev/ttyACM*')
    if not ports:
        print(f"[!]{indent} No /dev/ttyACM* devices found.")
        raise IndexError("No serial ports found")
    return ports[0]

def stop_serial_starter(port_name, indent=""):
    """Stops the Victron serial-starter service for a given port. Runs without sudo."""
    if not WINDOWS:
        port_name = port_name.split('/')[-1] # just in case we send dev/port_name
        try:
            # This script is specific to Victron VenusOS
            subprocess.run(["/opt/victronenergy/serial-starter/stop-tty.sh", port_name], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"[!]{indent} Stop serial starter command failed with return code: {e.returncode}")
        except FileNotFoundError:
            print(f"[*]{indent} The stop serial starter script does not exist. Skipping.")

def start_serial_starter(port_name, indent=""):
    """Starts the Victron serial-starter service for a given port. Runs without sudo."""
    if not WINDOWS:
        port_name = port_name.split('/')[-1] # just in case we send dev/port_name
        try:
            # This script is specific to Victron VenusOS
            subprocess.run(["/opt/victronenergy/serial-starter/start-tty.sh", port_name], check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"[!]{indent} Start serial starter command failed with return code: {e.returncode}")
        except FileNotFoundError:
            print(f"[*]{indent} The start serial starter script does not exist. Skipping.")

def send_boot_command(serial_port, indent=""):
    """Send boot command and verify response with retry logic."""
    for attempt in range(MAX_BOOT_RETRIES):
        try:
            with serial.Serial(serial_port, BAUDRATE, timeout=BOOT_COMMAND_TIMEOUT) as ser:
                ser.reset_input_buffer()
                
                print(f"[*]{indent} Attempt {attempt + 1}/{MAX_BOOT_RETRIES}: Sending '$D' to ESP32...")
                ser.write(b'$D')
                ser.flush()
                
                start_time = time.time()
                while time.time() - start_time < BOOT_COMMAND_TIMEOUT:
                    try:
                        if ser.in_waiting > 0:
                            response = ser.read(ser.in_waiting).decode('utf-8', errors='ignore')
                            print(f"[*]{indent} Received: {response.strip()}")
                            if "Triggering bootloader" in response:
                                print(f"[+]{indent} Bootloader trigger confirmed!")
                                return True
                    except OSError:
                        print(f"[*]{indent} Serial connection disconnected, bootloader trigger is likely successful.")
                        return True
                    time.sleep(0.1)
                print(f"[!]{indent} No response or incorrect response received.")
        except serial.SerialException as e:
            print(f"[!]{indent} Serial error on attempt {attempt + 1}: {e}")
        
        if attempt < MAX_BOOT_RETRIES - 1:
            print(f"[*]{indent} Waiting {BOOT_COMMAND_RETRY_DELAY} seconds before retry...")
            time.sleep(BOOT_COMMAND_RETRY_DELAY)
    
    print(f"[!]{indent} Failed to trigger bootloader after {MAX_BOOT_RETRIES} attempts.")
    return False

def get_firmware_version(serial_port, indent=""):
    """Send version command '$K' and parse the response with retry logic."""
    for attempt in range(MAX_FIRMWARE_RETRIES):
        try:
            with serial.Serial(serial_port, BAUDRATE, timeout=BOOT_COMMAND_TIMEOUT) as ser:
                ser.reset_input_buffer()
                print(f"[*]{indent} Attempt {attempt + 1}/{MAX_FIRMWARE_RETRIES}: Sending '$K' to ESP32...")
                ser.write(b'$K')
                ser.flush()
                
                time.sleep(0.5) # Give time for a response
                
                response_lines = []
                while ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        response_lines.append(line)

                if len(response_lines) >= 2 and "recieved debug command" in response_lines[0]:
                    version = response_lines[1]
                    print(f"[+]{indent} Firmware version: {version}")
                    return version
                elif response_lines:
                     print(f"[*]{indent} Received: {' '.join(response_lines)}")

        except serial.SerialException as e:
            print(f"[!]{indent} Serial error on attempt {attempt + 1}: {e}")
        
        if attempt < MAX_FIRMWARE_RETRIES - 1:
            print(f"[*]{indent} Waiting {BOOT_COMMAND_RETRY_DELAY} seconds before retry...")
            time.sleep(BOOT_COMMAND_RETRY_DELAY)
            
    print(f"[!]{indent} Failed to get firmware version after {MAX_FIRMWARE_RETRIES} attempts.")
    return None

def check_for_drive_label(target_label="ENERTYMBOOT", indent=""):
    """Check for a device label using blkid. NOTE: Runs without sudo."""
    try:
        # Since this script is run as root, sudo is not needed here.
        result = subprocess.run(['blkid', '-o', 'export'], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            # blkid can return non-zero if no devices are found. This is not a fatal error.
            return None

        for line in result.stdout.strip().split('\n\n'):
            if not line: continue
            device_info = dict(item.split('=', 1) for item in line.split('\n') if '=' in item)
            if device_info.get('LABEL') == target_label or device_info.get('LABEL_FATBOOT') == target_label:
                return device_info.get('DEVNAME')
    except FileNotFoundError:
        print(f"[!]{indent} 'blkid' command not found. Is it installed and in your PATH?")
    except Exception as e:
        print(f"[!]{indent} Error parsing blkid output: {e}")
    return None

def wait_for_usb_drive(indent=""):
    """Wait for the ESP32's UF2 USB drive to appear."""
    print(f"[*]{indent} Waiting for ESP32 USB drive to appear...")
    start_time = time.time()
    while time.time() - start_time < UF2_TIMEOUT:
        device_path = check_for_drive_label(indent=indent)
        if device_path:
            print(f"[+]{indent} Found USB drive at {str(device_path).strip()}")
            return device_path
        time.sleep(1)
    return None

def mount_drive(device_path, indent=""):
    """Mount the UF2 drive. NOTE: Runs without sudo."""
    os.makedirs(MOUNT_BASE, exist_ok=True)
    if os.path.ismount(MOUNT_BASE):
        print(f"[*] {MOUNT_BASE} is already a mount point. Unmounting first.")
        unmount_drive(MOUNT_BASE, indent)

    try:
        print(f"[*]{indent} Mounting {device_path} to {MOUNT_BASE}...")
        # Since this script is run as root, sudo is not needed here.
        uid, gid = 0, 0 # Run as root
        mount_options = f"uid={uid},gid={gid},umask=0000"
        subprocess.run(['mount', '-o', mount_options, device_path, MOUNT_BASE], check=True)
        print(f"[+]{indent} Drive mounted successfully at {MOUNT_BASE}")
        return MOUNT_BASE
    except subprocess.CalledProcessError as e:
        print(f"[!]{indent} Failed to mount drive: {e}")
        return None

def unmount_drive(mount_point, indent=""):
    """Unmount the drive. NOTE: Runs without sudo."""
    if not os.path.ismount(mount_point):
        return
    try:
        print(f"[*]{indent} Unmounting {mount_point}...")
        # Since this script is run as root, sudo is not needed here.
        subprocess.run(['umount', mount_point], check=True)
        print(f"[+]{indent} Drive unmounted successfully")
    except subprocess.CalledProcessError as e:
        print(f"[!]{indent} Failed to unmount drive: {e}")

def download_firmware(github_url, output_file="firmware.uf2"):
    """Download firmware from a given URL."""
    print(f"[*] Downloading firmware from {github_url}...")
    try:
        r = requests.get(github_url, stream=True, timeout=30)
        r.raise_for_status()
        with open(output_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print(f"[+] Firmware downloaded to {output_file}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[!] Failed to download firmware: {e}")
        return False

def copy_firmware_to_drive(uf2_path, mount_point, indent=""):
    """Copy firmware to the drive. NOTE: Runs without sudo."""
    dest_path = os.path.join(mount_point, os.path.basename(uf2_path))
    print(f"[*]{indent} Copying firmware to {dest_path}...")
    try:
        # Since this script is run as root, sudo is not needed here.
        subprocess.run(["cp", uf2_path, dest_path], check=True)
        subprocess.run(["sync"], check=True)
        print(f"[+]{indent} Firmware copied and synced successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[!]{indent} Failed to copy or sync firmware: {e}")
        return False

def wait_for_drive_to_disappear(indent=""):
    """Wait for the UF2 drive to disappear after flashing."""
    print(f"[*]{indent} Waiting for ESP32 to reboot and drive to disappear...")
    start_time = time.time()
    while time.time() - start_time < UF2_TIMEOUT:
        if not check_for_drive_label(indent=indent):
            print(f"[+]{indent} Drive disappeared. Update likely successful.")
            return True
        time.sleep(1)
    print(f"[!]{indent} Drive did not disappear in time.")
    return False

def convert_to_raw_url(github_url):
    """Converts a GitHub blob URL to a raw content URL."""
    if "github.com" in github_url and "/blob/" in github_url:
        raw_url = github_url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        print(f"[*] Converted GitHub URL to raw content URL: {raw_url}")
        return raw_url
    return github_url

def flash_firmware_with_retry(firmware_file, device_path, max_retries=UF2_FLASH_RETRIES, indent=""):
    """Attempt to flash firmware with retry logic."""
    for attempt in range(max_retries):
        print(f"[*]{indent} Firmware flash attempt {attempt + 1}/{max_retries}")
        mount_point = mount_drive(device_path, indent=indent)
        if not mount_point:
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return False

        if not copy_firmware_to_drive(firmware_file, mount_point, indent=indent):
            unmount_drive(mount_point, indent=indent)
            if attempt < max_retries - 1:
                time.sleep(5)
                continue
            return False

        # The drive unmounts automatically upon successful copy
        # We wait for it to disappear.
        if wait_for_drive_to_disappear(indent=indent):
            print(f"[+]{indent} Firmware flash successful on attempt {attempt + 1}!")
            return True
        else:
            print(f"[!]{indent} Drive did not disappear on attempt {attempt + 1}")
            unmount_drive(mount_point, indent=indent) # Force unmount if it's stuck
            if attempt < max_retries - 1:
                time.sleep(5)

    print(f"[!]{indent} All {max_retries} firmware flash attempts failed.")
    return False

def cleanup_mount_point():
    """Clean up any existing mount."""
    if os.path.ismount(MOUNT_BASE):
        unmount_drive(MOUNT_BASE)

def main():
    parser = argparse.ArgumentParser(description="Update firmware on an ESP32 device via UF2 bootloader.")
    parser.add_argument("github_url", help="Direct link to the .uf2 file in a public GitHub repo.")
    args = parser.parse_args()

    cleanup_mount_point()

    github_url = convert_to_raw_url(args.github_url)
    if not download_firmware(github_url):
        exit(1)

    print("[*] Checking for ESP32 device...")
    device_path = check_for_drive_label()
    serial_port = None
    
    if device_path:
        print(f"[+] ESP32 already in UF2 mode! Found drive at {device_path}")
    else:
        try:
            serial_port = find_serial_port()
            print(f"[*] Found serial port: {serial_port}")
            stop_serial_starter(serial_port, indent="  |")
            print("[*] Checking current firmware version...")
            get_firmware_version(serial_port, indent="  |")
            print("[*] Triggering bootloader...")
            if not send_boot_command(serial_port, indent="  |"):
                print("[!] Failed to trigger bootloader. Exiting.")
                start_serial_starter(serial_port, indent="  |")
                exit(1)
            device_path = wait_for_usb_drive(indent="  |")
            if not device_path:
                print("[!] USB drive not detected after bootloader trigger. Exiting.")
                start_serial_starter(serial_port, indent="  |")
                exit(1)
        except IndexError:
            print("[!] No serial port found and device not in UF2 mode. Is it connected?")
            exit(1)

    print("[*] Starting firmware flash process...")
    if not flash_firmware_with_retry("firmware.uf2", device_path, indent="  |"):
        print("[!] Firmware update failed after all attempts.")
        exit(1)

    print("[+] Firmware update process completed.")
    print("[*] Waiting for device to reboot and appear on serial port...")
    time.sleep(5)
    
    try:
        serial_port = find_serial_port(indent="  |")
        print(f"[*] Found new serial port: {serial_port}")
        stop_serial_starter(serial_port, indent="  |")
        print("[*] Checking new firmware version...")
        get_firmware_version(serial_port, indent="  |")
        start_serial_starter(serial_port, indent="  |")
    except IndexError:
        print("[!] Could not find serial port after update. Please check the device manually.")

if __name__ == "__main__":
    main()
