#!/usr/bin/env python3
import os
import time
import subprocess
import argparse
import serial
import requests
import glob
import shutil # Added for cross-platform file copying
import sys # Added for platform-specific path handling
import serial.tools.list_ports # Added for Windows serial port listing

BAUDRATE = 9600
UF2_TIMEOUT = 20  # seconds
UF2_FLASH_RETRIES = 3  # number of times to retry firmware upload
BOOT_COMMAND_TIMEOUT = 5  # seconds to wait for response
BOOT_COMMAND_RETRY_DELAY = 3  # seconds to wait before retrying
MAX_BOOT_RETRIES = 5  # maximum number of retries for boot command
MAX_FIRMWARE_RETRIES = 3  # maximum number of retries for firmware version check
WINDOWS = os.name == 'nt'

# On Windows, this will store the drive letter (e.g., 'D:')
# On Linux, it remains a base directory for mounting
MOUNT_BASE_LINUX = "/tmp/esp32_mount"
MOUNT_BASE = MOUNT_BASE_LINUX # Default for Linux, will be updated for Windows

def find_serial_port(indent=""):
    if WINDOWS:
        ports = serial.tools.list_ports.comports()
        if not ports:
            print(f"[!]{indent} No serial ports found.")
            raise IndexError("No serial ports found")
        
        # Look for a common ESP32 USB-to-Serial converter (e.g., CP210x, CH340, FTDI)
        # You might need to adjust these strings based on your specific ESP32 board
        for p in ports:
            print(f"[*]{indent} Found port: {p.device} - {p.description}")
            if "USB-SERIAL CH340" in p.description.upper() or \
               "CP210X" in p.description.upper() or \
               "USB SERIAL DEVICE" in p.description.upper() or \
               "UART" in p.description.upper(): # Generic check
                print(f"[+]{indent} Selected serial port: {p.device}")
                return p.device
        
        print(f"[!]{indent} No suitable ESP32 serial port found. Listing all available ports:")
        for p in ports:
            print(f"    {p.device} - {p.description}")
        raise IndexError("No suitable ESP32 serial port found")
    else:
        ports = glob.glob('/dev/ttyACM*')
        if not ports:
            print(f"[!]{indent} No /dev/ttyACM* devices found.")
            raise IndexError("No serial ports found")
        print(f"[+]{indent} Selected serial port: {ports[0]}")
        return ports[0]

def stop_serial_starter(port_name):
    if not WINDOWS:
        port_name = port_name.split('/')[-1] # just in case we send dev/port_name
        try:
            # Using absolute path for the script
            subprocess.run(["/opt/victronenergy/serial-starter/stop-tty.sh", port_name], check=True, 
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[*] Serial starter stopped for {port_name}.")
        except subprocess.CalledProcessError as e:
            print(f"[!] Stop serial starter command failed with return code {e.returncode}: {e.stderr.decode().strip()}")
        except FileNotFoundError:
            print("[!] The stop serial starter command or script does not exist. Please check the path: /opt/victronenergy/serial-starter/stop-tty.sh")
    else:
        print("[*] Skipping stop_serial_starter on Windows.")


def start_serial_starter(port_name):
    if not WINDOWS:
        port_name = port_name.split('/')[-1] # just in case we send dev/port_name
        try:
            # Using absolute path for the script
            subprocess.run(["/opt/victronenergy/serial-starter/start-tty.sh", port_name], check=True, 
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            print(f"[*] Serial starter started for {port_name}.")
        except subprocess.CalledProcessError as e:
            print(f"[!] Start serial starter command failed with return code {e.returncode}: {e.stderr.decode().strip()}")
        except FileNotFoundError:
            print("[!] The start serial starter command or script does not exist. Please check the path: /opt/victronenergy/serial-starter/start-tty.sh")
    else:
        print("[*] Skipping start_serial_starter on Windows.")

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
                                    if line.strip(): # Only print non-empty lines
                                        print(f"[*]{indent} Received: {line.strip()}")
                    except OSError as e:
                        print(f"[*]{indent} Serial connection disconnected, bootloader trigger is likely successful ({e})")
                        return True # This often happens as the device reboots into bootloader
                    
                    time.sleep(0.1)  # Small delay to avoid busy waiting
                
                # If we get here, we didn't receive the expected response within timeout
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
                            
                            lines = response_str.splitlines()
                            if len(lines) >= 2 and "recieved debug command" in lines[0]:
                                version_line = lines[1].strip()
                                print(f"[+]{indent} Firmware version: {version_line}")
                                return version_line
                            elif len(lines) == 1 and "recieved debug command" in lines[0]:
                                # Sometimes the version comes on the same line or immediately after
                                print(f"[*]{indent} Received: {lines[0].strip()}")
                                return "Unknown (command received, but no version string)"
                            elif lines:
                                for line in lines:
                                    if line.strip():
                                        print(f"[*]{indent} Received: {line.strip()}")

                    except OSError as e:
                        print(f"[*]{indent} Serial connection disconnected ({e})")
                        return False # Device might have rebooted
                    
                    time.sleep(0.1)  # Small delay to avoid busy waiting
                
                print(f"[!]{indent} No response received from ESP32")
                
        except serial.SerialException as e:
            print(f"[!]{indent} Serial error on attempt {attempt + 1}: {e}")
        
        # Wait before retrying (except on the last attempt)
        if attempt < MAX_FIRMWARE_RETRIES - 1:
            print(f"[*]{indent} Waiting {BOOT_COMMAND_RETRY_DELAY} seconds before retry...")
            time.sleep(BOOT_COMMAND_RETRY_DELAY)
    
    # If we get here, all attempts failed
    print(f"[!]{indent} Failed to get firmware version after {MAX_FIRMWARE_RETRIES} attempts")
    return False

def get_drive_label_windows(drive_path):
    """
    On Windows, get the volume label of a drive letter using subprocess (powershell).
    Returns None if label not found or error.
    """
    try:
        # PowerShell command to get volume label
        # Get-Volume -DriveLetter 'C' | Select-Object -ExpandProperty FileSystemLabel
        command = f"Get-Volume -DriveLetter '{drive_path[0]}' | Select-Object -ExpandProperty FileSystemLabel"
        result = subprocess.run(["powershell.exe", "-Command", command], capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        # print(f"Debug: Error getting drive label for {drive_path}: {e.stderr.strip()}")
        return None
    except Exception as e:
        # print(f"Debug: Unexpected error getting drive label for {drive_path}: {e}")
        return None

def check_for_drive_label(target_label="ENERTYMBOOT"):
    """
    Check if a device with the specified label is present.
    Returns device path (e.g., '/dev/sdb1' or 'D:\\') if found, None otherwise.
    """
    if WINDOWS:
        import string
        # Iterate through all possible drive letters
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                label = get_drive_label_windows(drive_path)
                if label and label.upper() == target_label.upper():
                    print(f"[*] Found drive '{drive_path}' with label '{label}'")
                    return drive_path
        return None
    else:
        # Original Linux implementation
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
            print(f"Error running blkid: {e.stderr.strip()}")
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
            # On Windows, set MOUNT_BASE to the found drive letter
            if WINDOWS:
                global MOUNT_BASE
                MOUNT_BASE = device_path
            return device_path
        time.sleep(1)
    return None

def mount_drive(device_path):
    """
    On Linux, mount the UF2 drive and return the mount point.
    On Windows, simply return the device_path as it's already "mounted" (assigned a drive letter).
    """
    if WINDOWS:
        # On Windows, the drive is already "mounted" by the OS, just return its path
        print(f"[*] Drive '{device_path}' is already available on Windows.")
        return device_path
    else:
        # Create mount point if it doesn't exist
        try:
            os.makedirs(MOUNT_BASE_LINUX, exist_ok=True)
            print(f"[*] Created mount point at {MOUNT_BASE_LINUX}")
        except PermissionError:
            print(f"[!] Permission denied creating {MOUNT_BASE_LINUX}")
            print("[!] Trying to create mount point with sudo...")
            try:
                subprocess.run(['sudo', 'mkdir', '-p', MOUNT_BASE_LINUX], check=True)
                print(f"[*] Created mount point at {MOUNT_BASE_LINUX} with sudo")
            except subprocess.CalledProcessError as e:
                print(f"[!] Failed to create mount point: {e}")
                return None
        
        # Check if already mounted
        try:
            result = subprocess.run(['mount'], capture_output=True, text=True)
            if device_path in result.stdout and MOUNT_BASE_LINUX in result.stdout:
                print(f"[*] Drive already mounted at {MOUNT_BASE_LINUX}")
                return MOUNT_BASE_LINUX
        except:
            pass
        
        # Mount the drive with proper permissions
        try:
            print(f"[*] Mounting {device_path} to {MOUNT_BASE_LINUX}...")
            # Mount with user permissions for FAT filesystem
            uid = os.getuid()
            gid = os.getgid()
            mount_options = f"uid={uid},gid={gid},umask=0000"
            subprocess.run(['sudo', 'mount', '-o', mount_options, device_path, MOUNT_BASE_LINUX], check=True)
            print(f"[+] Drive mounted successfully at {MOUNT_BASE_LINUX}")
            return MOUNT_BASE_LINUX
        except subprocess.CalledProcessError as e:
            print(f"[!] Failed to mount drive: {e}")
            return None

def unmount_drive(mount_point):
    """Safely unmount the drive (Linux specific)"""
    if WINDOWS:
        print(f"[*] Skipping unmount for {mount_point} on Windows (OS handles it).")
        return
    else:
        try:
            print(f"[*] Unmounting {mount_point}...")
            subprocess.run(['sudo', 'umount', mount_point], check=True)
            print("[+] Drive unmounted successfully")
        except subprocess.CalledProcessError as e:
            print(f"[!] Failed to unmount drive: {e}")

def download_firmware(github_url, output_file="firmware.uf2"):
    print(f"[*] Downloading firmware from GitHub...")
    try:
        r = requests.get(github_url, stream=True)
        r.raise_for_status() # Raise an exception for HTTP errors
        with open(output_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        print("[+] Firmware downloaded.")
    except requests.exceptions.RequestException as e:
        print(f"[!] Failed to download firmware: {e}")
        exit(1)
    except Exception as e:
        print(f"[!] An unexpected error occurred during download: {e}")
        exit(1)

def copy_firmware_to_drive(uf2_path, mount_point, indent=""):
    """Copy firmware file to the mounted UF2 drive"""
    if WINDOWS:
        dest_path = os.path.join(mount_point, os.path.basename(uf2_path))
        print(f"[*]{indent} Copying firmware to {dest_path}...")
        try:
            shutil.copy(uf2_path, dest_path)
            print(f"[+]{indent} Firmware copied successfully.")
            return True
        except PermissionError:
            print(f"[!] {indent} Permission denied when copying to {dest_path}.")
            print(f"[!] {indent} Ensure the drive is not write-protected and Python has necessary permissions.")
            return False
        except Exception as e:
            print(f"[!]{indent} Failed to copy firmware: {e}")
            return False
    else:
        # Original Linux implementation
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
        
        # Sync to ensure write is complete (Linux only)
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
        if not current_device or current_device.upper() != device_path.upper():
            print("[+] Drive disappeared. Update likely successful.")
            return True
        time.sleep(1)
    
    print("[!] Drive did not disappear in time.")
    return False

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
        
        # Mount the USB drive (or just confirm its presence on Windows)
        mount_point = mount_drive(device_path)
        if not mount_point:
            print(f"[!]{indent} Failed to prepare USB drive on attempt {attempt + 1}")
            if attempt < max_retries - 1:
                print(f"[*]{indent} Waiting 5 seconds before retry...")
                time.sleep(5)
                continue
            else:
                return False

        # Copy firmware to the mounted drive
        if not copy_firmware_to_drive(firmware_file, mount_point, indent=indent):
            print(f"[!]{indent} Failed to copy firmware on attempt {attempt + 1}")
            unmount_drive(mount_point) # This will be a no-op on Windows
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
            
            # Try to unmount manually before retry (Linux only)
            unmount_drive(mount_point) 
            
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
    """Clean up any existing mount (Linux specific)"""
    if WINDOWS:
        print("[*] Skipping cleanup_mount_point on Windows.")
        return
    try:
        if os.path.ismount(MOUNT_BASE_LINUX):
            unmount_drive(MOUNT_BASE_LINUX)
    except Exception as e:
        print(f"[!] Error during cleanup_mount_point: {e}")

def main():
    parser = argparse.ArgumentParser(description="Update ESP32 firmware via UF2.")
    parser.add_argument("github_url", help="Direct link to UF2 file in public GitHub repo")
    args = parser.parse_args()

    # Clean up any existing mounts (Linux only)
    cleanup_mount_point()

    github_url = convert_to_raw_url(args.github_url)

    # Download firmware
    download_firmware(github_url)

    # Check if ESP32 is already in UF2 mode
    print("[*] Checking if ESP32 is already in UF2 bootloader mode...")
    existing_device = check_for_drive_label()
    
    if existing_device:
        print(f"[+] ESP32 already in UF2 mode! Found drive at {existing_device}")
        device_path = existing_device
        # If on Windows, ensure MOUNT_BASE is set to the found drive
        if WINDOWS:
            global MOUNT_BASE
            MOUNT_BASE = device_path
    else:
        # ESP32 not in UF2 mode, trigger bootloader
        try:
            serial_port = find_serial_port()
        except IndexError as e:
            print(f"[!] Error: {e}. Make sure your ESP32 is connected and drivers are installed.")
            exit(1)
            
        print(f"[*] Found serial port: {serial_port}")

        # for victron gx, we need to stop the serial starter service (Linux only)
        stop_serial_starter(serial_port)

        # get the current firmware version
        print("[*] Checking current firmware version...")
        get_firmware_version(serial_port, indent="   |")

        # Trigger bootloader by sending command
        print("[*] Triggering bootloader...")
        if not send_boot_command(serial_port, indent="   |"):
            print("[!] Failed to trigger bootloader. Exiting.")
            start_serial_starter(serial_port) # Re-enable service on failure (Linux only)
            exit(1)

        # Wait for the USB drive to appear after triggering bootloader
        device_path = wait_for_usb_drive(indent="   |")
        if not device_path:
            print("[!] USB drive not detected after bootloader trigger. Exiting.")
            start_serial_starter(serial_port) # Re-enable service on failure (Linux only)
            exit(1)
        
        # Start the serial starter service again, as ESP32 is now in UF2 mode (Linux only)
        start_serial_starter(serial_port)

    # Mount the USB drive and flash firmware with retry logic
    print("[*] Preparing USB drive and flashing firmware...")
    if not flash_firmware_with_retry("firmware.uf2", device_path, indent="   |"):
        print("[!] Firmware update failed after all retry attempts.")
        print("[!] Consider checking ESP32 connection or trying again.")
        # No automatic reboot on Windows
        exit(1)

    print("[*] Checking firmware version after update...")
    time.sleep(1) # Give some time for the ESP32 to reboot
    try:
        serial_port = find_serial_port(indent="   |")
    except IndexError:
        print("[*]    | Retrying to find serial port after reboot...")
        time.sleep(3)  # Give more time for the ESP32 to come back up
        try:
            serial_port = find_serial_port()
        except IndexError:
            print("[!] Could not find serial port after update to verify firmware version.")
            print("[+] Firmware update might still have been successful.")
            exit(0) # Exit successfully even if version check fails due to port not reappearing immediately
    
    get_firmware_version(serial_port, indent="   |")
    print("[+] Firmware update process completed!")

if __name__ == "__main__":
    main()