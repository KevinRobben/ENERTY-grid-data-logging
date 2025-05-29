#!/usr/bin/env python3
"""
ESP32 Debug Commander - Send debug commands to ESP32 from Raspberry Pi
"""

import serial
import time
import glob
import sys
from enum import IntEnum

class DebugCommand(IntEnum):
    """Debug commands matching the ESP32 enum"""
    REGISTER_DEBUG_SEND_BACK_CONFIRMATION = 0x41  # 'A'
    REGISTER_DEBUG_CONFIRMATION = 0x42             # 'B'
    DEBUG_OPTIONS = 0x43                           # 'C'
    TRIGGER_BOOTLOADER = 0x44                      # 'D'
    PRINT_AND_CLEAR_FLASH_DEBUG_LOG = 0x45        # 'E'
    STREAM_DEBUG_MESSAGES = 0x46                   # 'F'
    ENABLE_FLASH_DEBUG_LOGGING = 0x47             # 'G'
    DISABLE_FLASH_DEBUG_LOGGING = 0x48            # 'H'
    GET_ESP_RESET_REASON = 0x49                   # 'I'
    GET_CT_CALIBRATION_TABLE = 0x4A               # 'J'
    GET_FIRMWARE_VERSION = 0x4B                   # 'K'

# Magic start byte (you'll need to define this based on your ESP32 code)
DEBUG_DEVICE_MAGIC_START = 0x24  # '$' - adjust this if different

def find_serial_port(indent=""):
    """Find the serial port for ESP32 communication"""
    ports = glob.glob('/dev/ttyACM*')
    if not ports:
        print(f"[!]{indent} No /dev/ttyACM* devices found.")
        raise IndexError("No serial ports found")
    return ports[0]

class ESP32DebugCommander:
    def __init__(self, port=None, baudrate=9600, timeout=2):
        """Initialize the debug commander"""
        self.port = port or find_serial_port()
        self.baudrate = baudrate
        self.timeout = timeout
        self.serial_conn = None
        self.registered = False
        
    def connect(self):
        """Connect to the ESP32"""
        try:
            print(f"Connecting to ESP32 on {self.port} at {self.baudrate} baud...")
            self.serial_conn = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            time.sleep(2)  # Give time for connection to stabilize
            print("Connected successfully!")
            return True
        except Exception as e:
            print(f"Error connecting to ESP32: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the ESP32"""
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("Disconnected from ESP32")
    
    def send_command(self, command, extra_option=None):
        """Send a debug command to the ESP32"""
        if not self.serial_conn or not self.serial_conn.is_open:
            print("Error: Not connected to ESP32")
            return False
        
        try:
            # Prepare the message
            message = bytearray([DEBUG_DEVICE_MAGIC_START, command])
            
            # Add extra option if provided
            if extra_option is not None:
                message.append(extra_option)
            
            # Send the command
            self.serial_conn.write(message)
            self.serial_conn.flush()
            
            print(f"Sent command: 0x{command:02X}")
            if extra_option is not None:
                print(f"With extra option: 0x{extra_option:02X}")
            
            # Wait for and read response
            time.sleep(0.1)  # Give ESP32 time to process
            return self.read_response()
            
        except Exception as e:
            print(f"Error sending command: {e}")
            return False
    
    def read_response(self, timeout=3):
        """Read response from ESP32"""
        if not self.serial_conn:
            return False
        
        start_time = time.time()
        response_lines = []
        
        while time.time() - start_time < timeout:
            if self.serial_conn.in_waiting > 0:
                try:
                    line = self.serial_conn.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"ESP32: {line}")
                        response_lines.append(line)
                except Exception as e:
                    print(f"Error reading response: {e}")
            time.sleep(0.01)
        
        return len(response_lines) > 0
    
    def register_debug_device(self):
        """Register this device for debug communication"""
        print("Registering debug device...")
        success = self.send_command(DebugCommand.REGISTER_DEBUG_SEND_BACK_CONFIRMATION)
        if success:
            self.registered = True
            print("Debug device registered successfully!")
        return success
    
    def get_debug_options(self):
        """Get available debug options"""
        print("Getting debug options...")
        return self.send_command(DebugCommand.DEBUG_OPTIONS)
    
    def trigger_bootloader(self):
        """Trigger ESP32 bootloader mode"""
        print("Triggering bootloader mode...")
        return self.send_command(DebugCommand.TRIGGER_BOOTLOADER)
    
    def print_and_clear_flash_log(self):
        """Print and clear flash debug log"""
        print("Printing and clearing flash debug log...")
        return self.send_command(DebugCommand.PRINT_AND_CLEAR_FLASH_DEBUG_LOG)
    
    def enable_serial_debug(self):
        """Enable serial debug message streaming"""
        print("Enabling serial debug messages...")
        return self.send_command(DebugCommand.STREAM_DEBUG_MESSAGES)
    
    def enable_flash_logging(self):
        """Enable flash debug logging"""
        print("Enabling flash debug logging...")
        return self.send_command(DebugCommand.ENABLE_FLASH_DEBUG_LOGGING)
    
    def disable_flash_logging(self):
        """Disable flash debug logging"""
        print("Disabling flash debug logging...")
        return self.send_command(DebugCommand.DISABLE_FLASH_DEBUG_LOGGING)
    
    def get_reset_reason(self):
        """Get ESP32 reset reason"""
        print("Getting ESP32 reset reason...")
        return self.send_command(DebugCommand.GET_ESP_RESET_REASON)
    
    def get_ct_calibration(self, ct_number):
        """Get CT calibration table for specified CT (1, 2, or 3)"""
        if ct_number not in [1, 2, 3]:
            print("Error: CT number must be 1, 2, or 3")
            return False
        
        print(f"Getting CT{ct_number} calibration table...")
        # Convert CT number to ASCII ('1', '2', '3')
        ct_ascii = ord(str(ct_number))
        return self.send_command(DebugCommand.GET_CT_CALIBRATION_TABLE, ct_ascii)
    
    def get_firmware_version(self):
        """Get firmware version"""
        print("Getting firmware version...")
        return self.send_command(DebugCommand.GET_FIRMWARE_VERSION)

def print_menu():
    """Print the command menu"""
    print("\n=== ESP32 Debug Commander ===")
    print("1. Register debug device")
    print("2. Get debug options")
    print("3. Trigger bootloader")
    print("4. Print and clear flash log")
    print("5. Enable serial debug messages")
    print("6. Enable flash logging")
    print("7. Disable flash logging")
    print("8. Get reset reason")
    print("9. Get CT calibration (specify CT 1, 2, or 3)")
    print("10. Get firmware version")
    print("0. Exit")
    print("=" * 30)

def main():
    """Main function"""
    commander = ESP32DebugCommander()
    
    if not commander.connect():
        sys.exit(1)
    
    try:
        while True:
            print_menu()
            choice = input("Enter your choice: ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                commander.register_debug_device()
            elif choice == '2':
                commander.get_debug_options()
            elif choice == '3':
                confirm = input("This will trigger bootloader mode. Continue? (y/N): ")
                if confirm.lower() == 'y':
                    commander.trigger_bootloader()
            elif choice == '4':
                commander.print_and_clear_flash_log()
            elif choice == '5':
                commander.enable_serial_debug()
            elif choice == '6':
                commander.enable_flash_logging()
            elif choice == '7':
                commander.disable_flash_logging()
            elif choice == '8':
                commander.get_reset_reason()
            elif choice == '9':
                ct_num = input("Enter CT number (1, 2, or 3): ").strip()
                try:
                    ct_number = int(ct_num)
                    commander.get_ct_calibration(ct_number)
                except ValueError:
                    print("Invalid CT number. Please enter 1, 2, or 3.")
            elif choice == '10':
                commander.get_firmware_version()
            else:
                print("Invalid choice. Please try again.")
            
            input("\nPress Enter to continue...")
    
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        commander.disconnect()

if __name__ == "__main__":
    main()