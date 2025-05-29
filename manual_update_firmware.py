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



BAUDRATE = 9600
UF2_TIMEOUT = 20  # seconds
UF2_FLASH_RETRIES = 3  # number of times to retry firmware upload
MOUNT_BASE = "/tmp/esp32_mount"
BOOT_COMMAND_TIMEOUT = 5  # seconds to wait for response
BOOT_COMMAND_RETRY_DELAY = 3  # seconds to wait before retrying
MAX_BOOT_RETRIES = 5  # maximum number of retries for boot command
MAX_FIRMWARE_RETRIES = 2  # maximum number of retries for firmware version check


def find_serial_port(indent=""):
    ports = glob.glob('/dev/ttyACM*')
    if not ports:
        print(f"[!]{indent} No /dev/ttyACM* devices found.")
        raise IndexError("No serial ports found")
    return ports[0]

def send_boot_command(serial_port, indent=""):
    """Send boot command and verify response with retry logic"""
    for attempt in range(MAX_BOOT_RETRIES):
        try:
            with serial.Serial(serial_port, BAUDRATE, timeout=BOOT_COMMAND_TIMEOUT) as ser:
                # Clear any existing data in the buffer
                ser.reset_input_buffer()
                
                print(f"[*]{indent} Attempt {attempt + 1}/{MAX_BOOT_RETRIES}: Sending '$D' to ESP32...")
                ser.write(b'$D')
                ser.flush()  # Ensure data is sent immediately
                
                # Read response with timeout
                start_time = time.time()
                response_buffer = b''
                
                while time.time() - start_time < BOOT_COMMAND_TIMEOUT:
                    try:
                        if ser.in_waiting > 0:
                            chunk = ser.read(ser.in_waiting)
                            response_buffer += chunk
                            
                            # Convert to string for checking
                            response_str = response_buffer.decode('utf-8', errors='ignore')
                            
                            
                            # Check if we got the expected response
                            if "Triggering bootloader" in response_str:
                                print(f"[+]{indent} Bootloader trigger confirmed!")
                                return True
                            else:
                                for line in response_str.splitlines():
                                    print(f"[*]{indent} Received: {line.strip()}")
                    except OSError as e:
                        print(f"[*]{indent} Serial connection disconnected, bootloader trigger is likely successful")
                        return True
                    
                    time.sleep(0.1)  # Small delay to avoid busy waiting
                
                # If we get here, we didn't receive the expected response
                response_str = response_buffer.decode('utf-8', errors='ignore')
                if response_str.strip():
                    print(f"[!]{indent} Unexpected response: {response_str.strip()}")
                else:
                    print(f"[!]{indent} No response received from ESP32")
                
        except serial.SerialException as e:
            print(f"[!]{indent} Serial error on attempt {attempt + 1}: {e}")
        
        # Wait before retrying (except on the last attempt)
        if attempt < MAX_BOOT_RETRIES - 1:
            print(f"[*]{indent} Waiting {BOOT_COMMAND_RETRY_DELAY} seconds before retry...")
            time.sleep(BOOT_COMMAND_RETRY_DELAY)
    
    # If we get here, all attempts failed
    print(f"[!]{indent} Failed to trigger bootloader after {MAX_BOOT_RETRIES} attempts")
    return False


def get_firmware_version(serial_port, indent=""):
    """Send version command and verify response with retry logic"""
    for attempt in range(MAX_FIRMWARE_RETRIES):
        try:
            with serial.Serial(serial_port, BAUDRATE, timeout=BOOT_COMMAND_TIMEOUT) as ser:
                # Clear any existing data in the buffer
                ser.reset_input_buffer()
                
                print(f"[*]{indent} Attempt {attempt + 1}/{MAX_FIRMWARE_RETRIES}: Sending '$K' to ESP32...")
                ser.write(b'$K')
                ser.flush()  # Ensure data is sent immediately
                
                # Read response with timeout
                start_time = time.time()
                response_buffer = b''
                
                while time.time() - start_time < BOOT_COMMAND_TIMEOUT:
                    try:
                        if ser.in_waiting > 0:
                            chunk = ser.read(ser.in_waiting)
                            response_buffer += chunk
                            
                            # Convert to string for checking
                            response_str = response_buffer.decode('utf-8', errors='ignore')
                            # Check if we got the expected response
                            if len(response_str.splitlines()) == 1:
                                print(f"[*]{indent} Received: {response_str.strip()}")
                                break  # No firmware version available, just a debug command response

                            # firmware version is the next line "vx.x.x" after recieved debug command
                            if "recieved debug command" in response_str:
                                print(f"[+]{indent} firmware version: {response_str.splitlines()[1].strip()}")
                                return response_str.splitlines()[1].strip()
                            
                    except OSError as e:
                        print(f"[*]{indent} Serial connection disconnected")
                        return False
                    
                    time.sleep(0.1)  # Small delay to avoid busy waiting
                
                print(f"[!]{indent} No response received from ESP32")
                
        except serial.SerialException as e:
            print(f"[!]{indent} Serial error on attempt {attempt + 1}: {e}")
        
        # Wait before retrying (except on the last attempt)
        if attempt < MAX_FIRMWARE_RETRIES - 1:
            print(f"[*]{indent} Waiting {2} seconds before retry...")
            time.sleep(BOOT_COMMAND_RETRY_DELAY)
    
    # If we get here, all attempts failed
    print(f"[!]{indent} Failed to get firmware version after {MAX_FIRMWARE_RETRIES} attempts")
    return False


def check_for_drive_label(target_label="ENERTYMBOOT"):
    """
    Check if a device with the specified label is present
    Returns device path if found, None otherwise
    """
    try:
        # Run blkid to get all block device info in JSON format
        result = subprocess.run(['sudo', 'blkid', '-o', 'export'], 
                              capture_output=True, text=True, check=True)
        
        # Parse blkid output (key=value pairs separated by blank lines)
        devices = []
        current_device = {}
        
        for line in result.stdout.strip().split('\n'):
            if line.strip() == '':
                if current_device:
                    devices.append(current_device)
                    current_device = {}
            else:
                if '=' in line:
                    key, value = line.split('=', 1)
                    current_device[key] = value
        
        # Don't forget the last device
        if current_device:
            devices.append(current_device)
        
        # Look for our target label
        for device in devices:
            if device.get('LABEL') == target_label or device.get('LABEL_FATBOOT') == target_label:
                return device.get('DEVNAME')
                
    except subprocess.CalledProcessError as e:
        print(f"Error running blkid: {e}")
    except Exception as e:
        print(f"Error parsing blkid output: {e}")
    
    return None

def wait_for_usb_drive(indent=""):
    print("[*] Waiting for ESP32 USB drive to appear...")
    start_time = time.time()
    while time.time() - start_time < UF2_TIMEOUT:
        device_path = check_for_drive_label()
        if device_path:
            print(f"[+]{indent} Found USB drive at {str(device_path).strip()}")
            return device_path
        time.sleep(1)
    return None

def mount_drive(device_path):
    """Mount the UF2 drive and return the mount point"""
    # Create mount point if it doesn't exist
    try:
        os.makedirs(MOUNT_BASE, exist_ok=True)
        print(f"[*] Created mount point at {MOUNT_BASE}")
    except PermissionError:
        print(f"[!] Permission denied creating {MOUNT_BASE}")
        print("[!] Trying to create mount point with sudo...")
        try:
            subprocess.run(['sudo', 'mkdir', '-p', MOUNT_BASE], check=True)
            print(f"[*] Created mount point at {MOUNT_BASE} with sudo")
        except subprocess.CalledProcessError as e:
            print(f"[!] Failed to create mount point: {e}")
            return None
    
    # Check if already mounted
    try:
        result = subprocess.run(['mount'], capture_output=True, text=True)
        if device_path in result.stdout and MOUNT_BASE in result.stdout:
            print(f"[*] Drive already mounted at {MOUNT_BASE}")
            return MOUNT_BASE
    except:
        pass
    
    # Mount the drive with proper permissions
    try:
        print(f"[*] Mounting {device_path} to {MOUNT_BASE}...")
        # Mount with user permissions for FAT filesystem
        uid = os.getuid()
        gid = os.getgid()
        mount_options = f"uid={uid},gid={gid},umask=0000"
        subprocess.run(['sudo', 'mount', '-o', mount_options, device_path, MOUNT_BASE], check=True)
        print(f"[+] Drive mounted successfully at {MOUNT_BASE}")
        return MOUNT_BASE
    except subprocess.CalledProcessError as e:
        print(f"[!] Failed to mount drive: {e}")
        return None

def unmount_drive(mount_point):
    """Safely unmount the drive"""
    try:
        print(f"[*] Unmounting {mount_point}...")
        subprocess.run(['sudo', 'umount', mount_point], check=True)
        print("[+] Drive unmounted successfully")
    except subprocess.CalledProcessError as e:
        print(f"[!] Failed to unmount drive: {e}")

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

def copy_firmware_to_drive(uf2_path, mount_point, indent=""):
    """Copy firmware file to the mounted UF2 drive"""
    if not os.path.ismount(mount_point):
        print(f"[!]{indent} {mount_point} is not a valid mount point")
        return False
    
    dest_path = os.path.join(mount_point, os.path.basename(uf2_path))
    print(f"[*]{indent} Copying firmware to {dest_path}...")
    
    # Check if we can write to the mount point
    if not os.access(mount_point, os.W_OK):
        print(f"[*]{indent} Using sudo for copy operation due to permission restrictions...")
        try:
            subprocess.run(["sudo", "cp", uf2_path, dest_path], check=True)
            print(f"[+]{indent} Firmware copied successfully with sudo.")
        except subprocess.CalledProcessError as e:
            print(f"[!]{indent} Failed to copy firmware with sudo: {e}")
            return False
    else:
        try:
            subprocess.run(["cp", uf2_path, dest_path], check=True)
            print(f"[+]{indent} Firmware copied successfully.")
        except subprocess.CalledProcessError as e:
            print(f"[!]{indent} Failed to copy firmware: {e}")
            return False
    
    # Sync to ensure write is complete
    try:
        subprocess.run(["sync"], check=True)
        print(f"[+]{indent} File system synced.")
    except subprocess.CalledProcessError as e:
        print(f"[!]{indent} Failed to sync filesystem: {e}")
    
    return True

def wait_for_drive_to_disappear(device_path):
    """Wait for the UF2 drive to disappear (indicating successful flash)"""
    print("[*] Waiting for ESP32 to reboot and drive to disappear...")
    start_time = time.time()
    
    while time.time() - start_time < UF2_TIMEOUT:
        current_device = check_for_drive_label()
        if not current_device or current_device != device_path:
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

def flash_firmware_with_retry(firmware_file, device_path, max_retries=UF2_FLASH_RETRIES, indent=""):
    """
    Attempt to flash firmware with retry logic
    Returns True if successful, False if all retries failed
    """
    for attempt in range(max_retries):
        print(f"[*]{indent} Firmware flash attempt {attempt + 1}/{max_retries}")
        
        # Mount the USB drive
        mount_point = mount_drive(device_path)
        if not mount_point:
            print(f"[!]{indent} Failed to mount USB drive on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                print(f"[*]{indent} Waiting 5 seconds before retry...")
                time.sleep(5)
                continue
            else:
                return False

        # Copy firmware to the mounted drive
        if not copy_firmware_to_drive(firmware_file, mount_point, indent=indent):
            print(f"[!]{indent} Failed to copy firmware on attempt {attempt + 1}")
            unmount_drive(mount_point)
            if attempt < max_retries - 1:
                print(f"[*]{indent} Waiting 5 seconds before retry...")
                time.sleep(5)
                continue
            else:
                return False

        # Wait for the drive to disappear (indicating successful flash)
        if wait_for_drive_to_disappear(device_path):
            print(f"[+]{indent} Firmware flash successful on attempt {attempt + 1}!")
            return True
        else:
            print(f"[!]{indent} Drive did not disappear on attempt {attempt + 1}")
            
            # Try to unmount manually before retry
            try:
                unmount_drive(mount_point)
            except:
                pass
            
            if attempt < max_retries - 1:
                print(f"[*]{indent} Retrying firmware upload in 5 seconds...")
                time.sleep(5)
                
                # Check if drive is still there for next attempt
                if not check_for_drive_label():
                    print(f"[!]{indent} Drive disappeared during retry wait - this might actually be success!")
                    return True
            else:
                print(f"[!]{indent} All {max_retries} firmware flash attempts failed")
                return False
    
    return False

def cleanup_mount_point():
    """Clean up any existing mount"""
    try:
        if os.path.ismount(MOUNT_BASE):
            unmount_drive(MOUNT_BASE)
    except:
        pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("github_url", help="Direct link to UF2 file in private GitHub repo")
    args = parser.parse_args()

    # Clean up any existing mounts
    cleanup_mount_point()

    github_url = convert_to_raw_url(args.github_url)
    github_token = load_github_token()

    # Download firmware
    download_firmware(github_url, github_token)

    # Check if ESP32 is already in UF2 mode
    print("[*] Checking if ESP32 is already in UF2 bootloader mode...")
    existing_device = check_for_drive_label()
    
    if existing_device:
        print(f"[+] ESP32 already in UF2 mode! Found drive at {existing_device}")
        device_path = existing_device
    else:
        # ESP32 not in UF2 mode, trigger bootloader
        serial_port = find_serial_port()
        print(f"[*] Found serial port: {serial_port}")

        # get the current firmware version
        print("[*] Checking current firmware version...")
        get_firmware_version(serial_port, indent="   |")

        # Trigger bootloader by sending command
        print("[*] Triggering bootloader...")
        if not send_boot_command(serial_port, indent="   |"):
            print("[!] Failed to trigger bootloader. Exiting.")
            exit(1)

        # Wait for the USB drive to appear after triggering bootloader
        device_path = wait_for_usb_drive(indent="   |")
        if not device_path:
            print("[!] USB drive not detected after bootloader trigger. Exiting.")
            exit(1)

    # Mount the USB drive and flash firmware with retry logic
    print("[*] Mounting USB drive and flashing firmware...")
    if not flash_firmware_with_retry("firmware.uf2", device_path, indent="   |"):
        print("[!] Firmware update failed after all retry attempts.")
        print("[!] Consider rebooting Raspberry Pi or checking ESP32 connection...")
        # Uncomment the line below if you want automatic reboot as fallback
        # subprocess.run(["sudo", "reboot"])
        exit(1)

    print("[*] Checking firmware version after update...")
    time.sleep(1)
    try:
        serial_port = find_serial_port(indent="   |")
    except IndexError:
        print("[*]   | Retrying")
        time.sleep(3)  # Give some time for the ESP32 to reboot
        # Find serial port and get firmware version
        serial_port = find_serial_port()
    
    get_firmware_version(serial_port, indent="   |")

if __name__ == "__main__":
    main()