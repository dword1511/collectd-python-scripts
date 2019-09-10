# ======================================================================
# i2cdev.py - I2C module to perform I2C operations using the i2c device
#             files in /dev. Written for the Raspberry Pi.
#
# Requires that the i2c-bcm2708 kernel module is installed. Check with
# the 'lsmod' command and load with the 'modprobe' command. The newest
# driver is required to perform combined transactions.
#
# Also requires the i2c-dev kernel module. This module provides the i2c
# device files as "/dev/i2c-X". Bus #0 is typically used with the camera
# module on S5. Bus #1 is available on the GPIO Connector. Bus #2 is
# not accessible (permanantly wired for HDMI).
#
# More documentation at https://i2c.wiki.kernel.org/index.php/Main_Page
#
# version 1.0 - cbeytas - June 23, 2013
# Tested with Python 2.7.1 and Python 3.2.3 ============================
import sys          # Used for sys.version for python3 compatibility
import ctypes       # C-style variables and structures.
import fcntl        # Used to perform ioctl on device files.

# ----------------------------------------------------------------------
# ctypes Structure Classes
class I2C_MSG_S(ctypes.Structure):
    '''i2c_msg structure from "i2c-dev.h" from i2c-tools.
    Defines a pure i2c read or write transaction.'''
    _fields_ = [("addr", ctypes.c_uint16),  # Slave address.
                ("flags", ctypes.c_uint16), # Bitmap of I2C_M_XXX values.
                ("len", ctypes.c_uint16),   # Number of bytes to write or read.
                ("buf", ctypes.c_char_p),]  # In/Out byte buffer.
I2C_MSG_P = ctypes.POINTER(I2C_MSG_S)

class I2C_RDWR_S(ctypes.Structure):
    '''i2c_rdwr_ioctl_data structure from "i2c-dev.h" from i2c-tools.
    Used to send pure I2C messages using the I2C_RDWR ioctl.'''
    _fields_ = [("i2c_msg", I2C_MSG_P),     # Array of i2c_msg pointers.
                ("nmsgs", ctypes.c_int),]   # Number of messages in the array.
# ----------------------------------------------------------------------
# I2C Functionality Bits
FUNCS = {"I2C_FUNC_I2C"                     : 0x00000001,
         "I2C_FUNC_10BIT_ADDR"              : 0x00000002,
         "I2C_FUNC_PROTOCOL_MANGLING"       : 0x00000004,
         "I2C_FUNC_SMBUS_PEC"               : 0x00000008,
         "I2C_FUNC_SMBUS_BLOCK_PROC_CALL"   : 0x00008000,
         "I2C_FUNC_SMBUS_QUICK"             : 0x00001000,
         "I2C_FUNC_SMBUS_READ_BYTE"         : 0x00002000,
         "I2C_FUNC_SMBUS_WRITE_BYTE"        : 0x00004000,
         "I2C_FUNC_SMBUS_READ_BYTE_DATA"    : 0x00008000,
         "I2C_FUNC_SMBUS_WRITE_BYTE_DATA"   : 0x00010000,
         "I2C_FUNC_SMBUS_READ_WORD_DATA"    : 0x00020000,
         "I2C_FUNC_SMBUS_WRITE_WORD_DATA"   : 0x00040000,
         "I2C_FUNC_SMBUS_PROC_CALL"         : 0x00080000,
         "I2C_FUNC_SMBUS_READ_BLOCK_DATA"   : 0x00100000,
         "I2C_FUNC_SMBUS_WRITE_BLOCK_DATA"  : 0x00200000,
         "I2C_FUNC_SMBUS_READ_I2C_BLOCK"    : 0x00400000,
         "I2C_FUNC_SMBUS_WRITE_I2C_BLOCK"   : 0x00800000,
         "I2C_FUNC_SMBUS_BYTE"              : 0x00006000,
         "I2C_FUNC_SMBUS_BYTE_DATA"         : 0x00018000,
         "I2C_FUNC_SMBUS_WORD_DATA"         : 0x00060000,
         "I2C_FUNC_SMBUS_BLOCK_DATA"        : 0x00300000,
         "I2C_FUNC_SMBUS_I2C_BLOCK"         : 0x00C00000,}
# Defined IOCTLs
I2C_RETRIES = 0x0701    # Number of times to retry a transfer (not used)
I2C_TIMEOUT = 0x0702    # Sets timeout in units of 10ms (not used)
I2C_SLAVE = 0x0703      # Change slave address (not used)
I2C_TENBIT = 0x0704     # 10-bit addressing (not used)
I2C_FUNCS = 0x0705      # Used by get_funcs() method
I2C_RDWR = 0x0707       # Main I2C transfer IOCTL
I2C_PEC = 0x0708        # Packet Error Checking (not used)
I2C_SMBUS = 0x0720      # SMBus transfers (not used)
# I2C Message Read/Write Bits
I2C_M_WR = 0x00
I2C_M_RD = 0x01
# ----------------------------------------------------------------------

class I2C:
    """Class for I2C communication using device files (/dev/i2c-X).

    The "i2c-dev" kernel module must be installed.

    Attributes:
        device = Filename of device being accessed.
        name = Name of device from /sys/class/i2c-dev/"device"/name.
        addr = Slave address (set manually or with set_addr() method).
    """
    def __init__(self, bus=None):
        '''Initialize object. If 'bus' is specified, tries to open the
        respective "/dev/i2c-X" file. May raise IOError on failure.'''
        # Initialize attributes
        self.device = ""
        self.name = ""
        self.addr = None
        self._dev = None
        if bus is not None:
            self.open(bus)

    def open(self, bus):
        '''Attempts to open the given i2c bus number (/dev/i2c-X).
        Will raise IOError on failure.'''
        ## Attempt to open device (allow IOError to be raised)
        ## We open in read-only mode since we only use IOCTLs.
        self.device = "i2c-%s" % bus
        self._dev = open("/dev/%s" % self.device, 'rb')
        # Try to lookup device name
        try:
            info = open("/sys/class/i2c-dev/%s/name" % self.device)
            self.name = info.readline().strip()
        except IOError as e:
            #print("/sys/class/i2c-dev",e)
            self.name = ""

    def close(self):
        '''Close any open device, reset attributes.'''
        if self._dev is not None:
            self._dev.close()
        self.device = ""
        self.name = ""
        self.addr = None
        self._dev = None

    def get_funcs(self):
        '''Return a dictionary with the functionality of the driver.

        Each key in the dictionary is an I2C_FUNC_XXX string with the
        value set to True if supported, and False if unsupported.
        Raises IOError if the I2C_FUNCS ioctl call fails.
        '''
        if self._dev is None:
            raise IOError("Device not open")
        # Instantiate an unsigned long ctypes variable
        funcs = ctypes.c_ulong()        
        # Attempt to perform I2C_FUNCS ioctl (allow IOError to be raised).
        ret = fcntl.ioctl(self._dev.fileno(), I2C_FUNCS, funcs)
        # Parse results into a dictionary and return
        return {key : True if funcs.value & val else False
                for key,val in FUNCS.iteritems()}

    def set_addr(self, addr):
        '''Sets the slave address used for transactions.'''
        self.addr = int(addr)

    def set_timeout(self, timeout):
        '''Sets the I2C timeout using the I2C_TIMEOUT IOCTL.

        'timeout' is specified in units of 10ms.
        Note: Requires newest driver to support.
        Will raise IOError if the I2C_TIMEOUT ioctl call fails.
        '''
        if self._dev is None:
            raise IOError("Device not open")
        # Attempt to perform I2C_TIMEOUT ioctl (allow IOError to be raised).
        ret = fcntl.ioctl(self._dev.fileno(), I2C_TIMEOUT, timeout)
        return ret

    def read(self, nRead, addr=None):
        '''Reads a number of bytes from the slave address.

        It sends an I2C read message to the slave address 'addr'.
        If 'addr' is not specified, the slave address set with the
        set_addr() function is used.

        Format:
        S Addr Rd [A] [byte1] A ... [byte(nRead)] NA P

        The master will address the slave for a read, and acknowledge
        each byte with an ACK [A] up to the last expected byte which it
        will not acknowledge [NA], then end with a Stop (P) condition.

        Raises IOError if the slave does not acknowledge its address or
        if a clock stretch timeout occurs.
        Raises ValueError if no slave address found or 'nRead' invalid.
        '''
        if self._dev is None:
            raise IOError("Device not open")
        if addr is None:
            addr = self.addr
        if addr is None:
            raise ValueError("No slave address specified!")
        if 0 > nRead > 65535:
            raise ValueError("Number of bytes must be 0 - 65535")
#        print("Reading %d bytes from slave 0x%02X" % (nRead, addr))
        # Instantiate i2c_msg read structure (fill in all values but 'buf')
        read_msg = I2C_MSG_S(addr, I2C_M_RD, nRead, None)
        # Create buffer to accept data
        read_data = ctypes.create_string_buffer(nRead)
        read_msg.buf = ctypes.cast(read_data, ctypes.c_char_p)
        # Instantitate i2c_rdwr_ioctl_data structure (single message)
        rdwr = I2C_RDWR_S(ctypes.pointer(read_msg), 1)
        # Attempt to perform I2C read transaction using I2C_RDWR ioctl.
        ret = fcntl.ioctl(self._dev.fileno(), I2C_RDWR, rdwr)
        if ret != 1:
            raise IOError("Tried to send 1 message but %d sent" % ret, ret)
        # Return read buffer as list of integers
        return [ord(c) for c in read_data]        

    def write(self, data, addr=None):
        '''Writes a number of bytes to the slave address.

        Send an I2C write message to the slave address 'addr' with bytes
        from 'data' (list of integers). If 'addr' is not specified, the
        slave address that was set with the set_addr() function is used.

        Format:
        S Addr Wr [A] data1 [A] ... P

        The slave must acknowledge its slave address and each byte sent
        or IOError will be raised. Ends with a Stop (P) condition.

        Raises ValueError if no slave address found.
        '''
        if self._dev is None:
            raise IOError("Device not open")
        if addr is None:
            addr = self.addr
        if addr is None:
            raise ValueError("No slave address specified!")
        if len(data) > 32767:
            raise ValueError("Cannot write more than 32767 bytes at a time.")
#        print("Writing %d bytes to slave 0x%02X" % (len(data), addr))
        # Instantiate i2c_msg write structure (fill in all values but 'buf')
        write_msg = I2C_MSG_S(addr, I2C_M_WR, len(data), None)
        # Set write buffer (Python3 compatibility: convert string to bytes)
        if sys.version < '3':
            write_msg.buf = "".join(chr(x & 0xFF) for x in data)
        else:
            write_msg.buf = "".join(chr(x & 0xFF) for x in data).encode("L1")
        # Instantitate i2c_rdwr_ioctl_data structure (single message)
        rdwr = I2C_RDWR_S(ctypes.pointer(write_msg), 1)
        # Attempt to perform I2C write transaction using I2C_RDWR ioctl.
        ret = fcntl.ioctl(self._dev.fileno(), I2C_RDWR, rdwr)
        if ret != 1:
            raise IOError("Tried to send 1 message but %d sent" % ret, ret)
        return ret

    def rdwr(self, data, nRead, addr=None):
        '''Perform a combined write/read transaction with the slave.

        Use the RDWR IOCTL to send a write followed by a read with no
        stop (P) in between (technically should be called WRRD). After
        a repeated start (S) the specified number of bytes is read.

        Format:
        S Addr Wr [A] data0 [A] ...[A] S Addr Rd [A] read0 [A] ...[A] P
        
        This is effectively an atomic write/read operation that prevents
        another master from taking control of the bus in between.
        
        'data' is a sequence of integers to write.
        'nread' is the number of bytes expected in response.
        'addr' is the destination slave address. If not specified the
        address that was set with the set_addr() method is used.

        Returns the bytes read from the slave as a list of integers.

        Will raise IOError if the transaction fails.
        Will raise ValueError if no slave address found or if the write
        data exceeds 16 bytes (Raspberry Pi BCM2385 limit).

        NOTE: Requires the latest 'i2c-bcm2708' driver! The original
              driver does not support combined transactions!
        '''
        if self._dev is None:
            raise IOError("Device not open")
        if addr is None:
            addr = self.addr
        if addr is None:
            raise ValueError("No slave address specified!")
        if len(data) > 16:
            raise ValueError("Write data exceeds BCM2835 FIFO size!")
        if 0 > nRead > 32767:
            raise ValueError("Number of bytes must be 0 - 32767")
        # Instantiate write i2c_msg structure (fill in all values but 'buf')
        write_msg = I2C_MSG_S(addr, I2C_M_WR, len(data), None)
        # Set write buffer (Python3 compatibility: convert string to bytes)
        if sys.version < '3':
            write_msg.buf = "".join(chr(x & 0xFF) for x in data)
        else:
            write_msg.buf = "".join(chr(x & 0xFF) for x in data).encode("L1")
        # Clip nRead to a sane number (short int)
        nRead &= 0x7FFF
        # Instantiate read i2c_msg structure (clip nRead to 65535 bytes max)
        read_msg = I2C_MSG_S(addr, I2C_M_RD, nRead, None)
        read_data = ctypes.create_string_buffer(nRead)
        read_msg.buf = ctypes.cast(read_data, ctypes.c_char_p)
        # Instantiate i2c_msg array of two pointers.
        msgs = (I2C_MSG_S * 2)(write_msg, read_msg)
        # Instantitate i2c_rdwr_ioctl_data structure
        rdwr = I2C_RDWR_S(msgs, 2)
        # Attempt to perform I2C transaction using I2C_RDWR ioctl.
        ret = fcntl.ioctl(self._dev.fileno(), I2C_RDWR, rdwr)
        if ret != 2:
            raise IOError("Tried to send 2 messages but %d sent" % ret, ret)
        # Return read buffer as list of integers
        return [ord(c) for c in read_data]        
#end class I2C



# ----------------------------------------------------------------------
# Sample program if module is run as __main__
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys
    if len(sys.argv) <= 1:
        # No Arguments: Print list of buses available
        print("Available I2C buses:")
        num = 0
        while True:
            try:
                bus = I2C(num)
            except IOError as e:
                # Stop scanning on first failure
                print(e)
                print("Stopped at I2C bus %d" % (num))
                break
            print(bus.device, bus.name)
            num += 1
    else:
        # One Argument: Perform i2cdetect on specified bus
        try:
            bus = I2C(int(sys.argv[1]))
        except (ValueError, IOError) as e:
            print(e)
            print("Cannot open /dev/i2c-%s" % sys.argv[1])
            sys.exit(1)
        print("Devices on bus /dev/%s (%s)" % (bus.device, bus.name))
        ## Scan valid I2C 7-bit address range, avoiding invalid addresses:
        ## (0-2=Different bus formats, 120-127=Reserved/10bit addresses)
        ## NOTE: If the SDA line is being held LOW, it will appear that
        ##       devices are present at all slave addresses.
        found = []
        for addr in range(3, 120):
            try:
                ## Taken from i2cdetect.c - Do not perform write operations on
                ## addresses that might contain EEPROMs to avoid corruption.
                if addr in range(0x30, 0x38) or addr in range(0x50, 0x60):
                    # Do a 1-byte read to see if a device exists at address.
                    bus.read(1, addr=addr);
                else:
                    # Do a 0-byte write to see if a device acknowledges.
                    bus.write([], addr=addr);
            except (IOError) as e:
                # No ACK. Address is vacant.
                pass
            else:
                # Transaction was ACK'd. Found a device.
                found.append(addr)
        # Display scan in a format similar to the "i2cdetect" command.
        print("     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f")
        for row in range(8):
            print("%d0: %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s %s " %
                  tuple([row]+["%02X" % addr if addr in found else "--"
                               for addr in range(row*16, row*16+16)]))
            
   
