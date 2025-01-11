import copy
import select
import struct
import logging
import socket
import sys
import time
import serial
import serial.tools.list_ports
import subprocess

VID = 0x239A
PID = 0x80A4

# Open the serial port
WINDOWS = sys.platform.startswith('win')

"""struct VictronSerialAmpsAndVoltage {
        uint8_t magic_start; // * 
        uint8_t command;     // C
        bool export_CT1;
        bool export_CT2;
        bool export_CT3;
        uint32_t I1; // mA
        uint32_t I2;
        uint32_t I3;
        uint32_t U1; // mV
        uint32_t U2;
        uint32_t U3;
        uint32_t P1; // W
        uint32_t P2;
        uint32_t P3;
    };"""

class VictronSerialAmpsAndVoltage:
    def __init__(self) -> None:
        self.command: int = 0
        self.export_CT1: bool = False
        self.export_CT2: bool = False
        self.export_CT3: bool = False
        self.I1: int = 0 # mA
        self.I2: int = 0
        self.I3: int = 0
        self.U1: int = 0 # mV
        self.U2: int = 0
        self.U3: int = 0
        self.P1: int = 0 # Watt
        self.P2: int = 0
        self.P3: int = 0 
        self.energy_forward: int = 0 # Wh
        self.energy_reverse: int = 0
        
    
    def set_all_to_zero(self):
        self.I1 = 0
        self.I2 = 0
        self.I3 = 0
        self.U1 = 0
        self.U2 = 0
        self.U3 = 0
        self.P1 = 0
        self.P2 = 0
        self.P3 = 0

    def __str__(self) -> str:
        return f"command: {self.command}, AC Phase L1: {self.U1 / 1000}V {self.I1 / 1000}A {self.P1 / 1000}W. AC Phase L2: {self.U2 / 1000}V {self.I2 / 1000}A {self.P2 / 1000}W. AC Phase L3: {self.U3 / 1000}V {self.I3 / 1000}A {self.P3 / 1000}W  -  ENERGY -> Forward: {self.energy_forward / 1000}kWh. Deverse: {self.energy_reverse / 1000}kWh"


class ModuleM:

    def __init__(self):
        self.ser = serial.Serial(None, 9600, timeout=0, rtscts=False, dsrdtr=False, xonxoff=False)
        self.datagram = b""
        self.serialnumber = None
        self.mmdata = VictronSerialAmpsAndVoltage()
        self.mmregistered = False # module m registered with *B command
        self.last_update = time.time()
        self.mmregistered_last_register_request = time.time()

        # communication signals for dbus-homemanager
        self.new_port_name = False
        self.new_serialnumber = False
        self.errors = []
        self.errors_show_index = 0 # the current displayed error in victron

    def _read_data(self):
        try:
            in_waiting = self.ser.in_waiting
            ready = in_waiting > 0
        except Exception as e: # attribute error is thrown when no port passed to serial.Serial
            logging.info("Serial port closed")
            self.mmregistered = False
            if self.ser.port is not None and self.ser.is_open:
                self.ser.close()
            for port in serial.tools.list_ports.comports():
                if port.vid == VID and port.pid == PID:
                    port_name = port.name
                    self.ser.port = port_name
                    self.new_port_name = True
                    logging.info(f"Found Module M on {port_name}")
                    self.ser.open()
                    in_waiting = self.ser.in_waiting
                    ready = in_waiting > 0
                    break
            else:
                logging.info("Module M not found")
                return False
            
        if not self.mmregistered and time.time() - self.mmregistered_last_register_request > 2:
            self.mmregistered_last_register_request = time.time()
            logging.info("Registering Debug, sending $A")
            try:
                self.ser.write(b'$A') # RegisterDebug_sendBackConfirmation
            except serial.SerialException as e:
                logging.error(f'Could not write to serial port: { e.args[0]}')
            return False

        if not ready and self.datagram == b'':
            # logging.info('no data ready')
            return False

        self.datagram += self.ser.read(in_waiting)
        if len(self.datagram) == 0: 
            return False
        return True
    
    def send_uf2_command(self):
        if not self.mmregistered:
            return
        logging.info("sending uf2 command")
        try:
            self.ser.write(b'$D') # uf2 bootloader
        except serial.SerialException as e:
            logging.error(f'Could not write to serial port: { e.args[0]}')


    def _decode_data(self):   
        self.last_update = time.time()

        if not self.mmregistered:
            # search for the registration command inside the datagram
            while len(self.datagram) > 2 and self.datagram[:2] != b'$B': # remove garbage data until we find RegisterVictronGXConfirmation
                self.datagram = self.datagram[1:]

            if len(self.datagram) >= 13:
                self.mmregistered = True
                self.datagram = self.datagram[2:13]
                self.serialnumber = copy.deepcopy(self.datagram).decode('ascii')
                self.new_serialnumber = True
                self.datagram = b''
                logging.info(f"Module M registered with serialnumber: {self.serialnumber}")
                return False
            logging.info(f'module m not registered, trowing away data: {self.datagram}')
            self.datagram = b""
            return False

        data = self.datagram.replace(b'\r', b'').split(b'\n')
        for line in data:
            logging.info(line.decode('ascii'))
        self.datagram = b''
        return True

if __name__ == "__main__":
    start_time = time.time()
    send_uf2 = False

    logging.basicConfig(level=logging.INFO)
    sma = ModuleM()
    for port in serial.tools.list_ports.comports():
            logging.info(f"{port.vid}, {port.pid}, desc: {port.name}")
    while True:

        if sma._read_data() and sma._decode_data():
            # logging.info(sma.mmdata)
            # if start_time + 10 < time.time() and not send_uf2:
            #     sma.send_uf2_command()
            #     send_uf2 = True
            pass
        else:
            if sma.last_update + 5 < time.time():
                logging.info('not updated for 5 seconds')
                sma.mmdata.set_all_to_zero()
        time.sleep(1)
    