#!/usr/bin/env python3
import os
import time
import subprocess
import argparse
import serial
import glob
from datetime import datetime

BAUDRATE = 9600
LOG_COMMAND_TIMEOUT = 10  # seconds to wait for response
LOG_COMMAND_RETRY_DELAY = 3  # seconds to wait before retrying
MAX_LOG_RETRIES = 5  # maximum number of retries for log command
WINDOWS = os.name == 'nt'

def find_serial_port(indent=""):
    """Find the first available /dev/ttyACM port."""
    if WINDOWS:
        import serial.tools.list_ports
        ports = [port.device for port in serial.tools.list_ports.comports()]
    else:
        ports = glob.glob('/dev/ttyACM*')
    
    if not ports:
        print(f"[!]{indent} No serial ports found.")
        raise IndexError("No serial ports found")
    return ports[0]

def stop_serial_starter(port_name, indent=""):
    """Stops the Victron serial-starter service for a given port. Runs without sudo."""
    if not WINDOWS:
        port_name = port_name.split('/')[-1] 
        try:
            subprocess.run(["/opt/victronenergy/serial-starter/stop-tty.sh", port_name], check=True, capture_output=True)
            print(f"[*]{indent} Stopped serial starter for {port_name}")
        except subprocess.CalledProcessError as e:
            print(f"[!]{indent} Stop serial starter command failed with return code: {e.returncode}")
        except FileNotFoundError:
            print(f"[*]{indent} The stop serial starter script does not exist. Skipping.")

def start_serial_starter(port_name, indent=""):
    """Starts the Victron serial-starter service for a given port. Runs without sudo."""
    if not WINDOWS:
        port_name = port_name.split('/')[-1] 
        try:
            subprocess.run(["/opt/victronenergy/serial-starter/start-tty.sh", port_name], check=True, capture_output=True)
            print(f"[*]{indent} Started serial starter for {port_name}")
        except subprocess.CalledProcessError as e:
            print(f"[!]{indent} Start serial starter command failed with return code: {e.returncode}")
        except FileNotFoundError:
            print(f"[*]{indent} The start serial starter script does not exist. Skipping.")

def get_logs(serial_port, indent=""):
    """Send log request command '$K' and retrieve the logs with retry logic."""
    for attempt in range(MAX_LOG_RETRIES):
        try:
            with serial.Serial(serial_port, BAUDRATE, timeout=LOG_COMMAND_TIMEOUT) as ser:
                ser.reset_input_buffer()
                
                print(f"[*]{indent} Attempt {attempt + 1}/{MAX_LOG_RETRIES}: Sending '$K' to ESP32...")
                ser.write(b'$K')
                ser.flush()
                
                time.sleep(0.5) 
                
                response_lines = []
                while True:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        if not ser.in_waiting:
                            break
                    response_lines.append(line)

                if response_lines:
                    print(f"[+]{indent} Logs received successfully.")
                    return "\n".join(response_lines)
                else:
                    print(f"[*]{indent} No response received.")

        except serial.SerialException as e:
            print(f"[!]{indent} Serial error on attempt {attempt + 1}: {e}")
        
        if attempt < MAX_LOG_RETRIES - 1:
            print(f"[*]{indent} Waiting {LOG_COMMAND_RETRY_DELAY} seconds before retry...")
            time.sleep(LOG_COMMAND_RETRY_DELAY)
            
    print(f"[!]{indent} Failed to get logs after {MAX_LOG_RETRIES} attempts.")
    return None

def main():
    parser = argparse.ArgumentParser(description="Retrieve logs from an ESP32 device.")
    parser.add_argument("--output", "-o", help="File to save the logs to. If not provided, logs are printed to the console.", default=None)
    args = parser.parse_args()

    try:
        serial_port = find_serial_port()
        print(f"[*] Found serial port: {serial_port}")
    except IndexError:
        print("[!] No serial port found. Is the ESP32 connected?")
        exit(1)

    stop_serial_starter(serial_port, indent="  |")
    
    print("[*] Requesting logs from ESP32...")
    logs = get_logs(serial_port, indent="  |")
    
    start_serial_starter(serial_port, indent="  |")

    if logs:
        if "logs are empty" in logs.lower():
            print("[*] The device reported that the logs are empty.")
        else:
            if args.output:
                try:
                    with open(args.output, 'w') as f:
                        f.write(logs)
                    print(f"[+] Logs saved to {args.output}")
                except IOError as e:
                    print(f"[!] Error writing to file {args.output}: {e}")
            else:
                print("\n--- ESP32 Logs ---")
                print(logs)
                print("--- End of Logs ---\n")
    else:
        print("[!] Failed to retrieve logs.")
        exit(1)

if __name__ == "__main__":
    main()