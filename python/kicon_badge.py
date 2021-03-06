# Copyright (c) 2019 Maciej Suminski <orson@orson.net.pl>
#
# This source code is free software; you can redistribute it
# and/or modify it in source code form under the terms of the GNU
# General Public License as published by the Free Software
# Foundation; either version 2 of the License, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

## @package docstring
# Python library supporting the KiCon '19 badge

import serial
import struct
import time
import binascii
import commands_def as cmd_defs

class KiconBadge:
    LED1 = 0
    LED2 = 1

    BUT_RIGHT = 1
    BUT_LEFT  = 2
    BUT_DOWN  = 4
    BUT_UP    = 8

    BLACK = 0
    WHITE = 1

    LCD_WIDTH = 128
    LCD_HEIGHT = 64

    def __init__(self, port):
        self._serial = None
        self._serial = serial.Serial(port, 115200, timeout=0.5)   # TODO baud?

    def __del__(self):
        if self._serial:
            self._serial.close()

    # Calculates CRC for transferred data
    def _crc(self, data):
        crc = 0

        try:
            for c in data:
                crc = crc ^ c
        except TypeError:
            crc = data  # handle int

        return crc

    # Creates a response packet. Used for veryifying badge response.
    def _make_resp(self, resp):
        return struct.pack('>BBB', 1, resp, self._crc(resp))

    # Creates a command packet
    def _make_cmd(self, cmd, data=None):
        if data != None:
            data_bytes = struct.pack('>B%ds' % len(data), cmd, data)
            data_len = len(data_bytes)
            return struct.pack('>B%dsB' % data_len,    # struct format
                    data_len, data_bytes, self._crc(data_bytes))
        else:
            return struct.pack('>BBB', 1, cmd, self._crc(cmd))

    # Receives and validates response from the badge. Returns raw data (if any).
    def _get_resp(self):
        resp_len = self._serial.read(1)[0]
        resp_data = self._serial.read(resp_len + 1) # +1 for CRC
        resp_type = resp_data[0]
        resp_crc = resp_data[-1]
        calc_crc = self._crc(resp_data[:-1])
        raw_data = resp_data[1:-1]      # strip command response type and CRC

        if resp_crc != calc_crc:
            raise Exception('CRC error (expected 0x%x, got 0x%x)'
                    % (calc_crc, resp_crc))

        if resp_type != cmd_defs.CMD_RESP_OK:
            raise Exception('Response != OK: response = 0x%.2x, data = "%s"'
                    % (resp_type, str(binascii.hexlify(raw_data), 'ascii')))

        return raw_data

    ## Initializes the badge to a valid state.
    #
    # Should be called whenever the badge state is unknown.
    def init(self):
        # special command type, cannot be created with make_cmd
        reset_cmd = struct.pack('>B', cmd_defs.CMD_TYPE_RESET)
        reset_resp = self._make_resp(cmd_defs.CMD_RESP_RESET)

        self._serial.write(reset_cmd)
        time.sleep(0.1)
        self._serial.read(len(reset_resp))

        trials = 0
        while self._serial.read(len(reset_resp)) != reset_resp:
            self._serial.write(reset_cmd)
            trials = trials + 1
            time.sleep(0.1)

            if trials == 256:
                raise Exception('No response after reset')

    ## Transfers data over UART.
    #
    # @param data are bytes to be sent
    # @return Received data (if any).
    def uart_transfer(self, data):
        cmd = self._make_cmd(cmd_defs.CMD_TYPE_UART, data)
        self._serial.write(cmd)
        return self._get_resp()

    ## Clears the display buffer.
    def lcd_clear(self):
        cmd = self._make_cmd(cmd_defs.CMD_TYPE_LCD,
                struct.pack('>B', cmd_defs.CMD_LCD_CLEAR))
        self._serial.write(cmd)
        self._get_resp()

    ## Redraws the display buffer.
    def lcd_refresh(self):
        cmd = self._make_cmd(cmd_defs.CMD_TYPE_LCD,
                struct.pack('>B', cmd_defs.CMD_LCD_REFRESH))
        self._serial.write(cmd)
        self._get_resp()

    ## Draws a pixel in the display buffer.
    #
    # @param x is the horizontal coordinate (0-127).
    # @param y is the vertical coordinate (0-63).
    # @param color is the pixel color (BLACK [0] or WHITE [1]).
    def lcd_pixel(self, x, y, color):
        cmd = self._make_cmd(cmd_defs.CMD_TYPE_LCD,
                struct.pack('>BBBB', cmd_defs.CMD_LCD_PIXEL, x, y, color))
        self._serial.write(cmd)
        self._get_resp()

    ## Draws a text in the display buffer.
    #
    # @param row is the row number (0-7).
    # @param col is the column number (0-63).
    # @param text is the string to be drawn.
    def lcd_text(self, row, col, text):
        cmd = self._make_cmd(cmd_defs.CMD_TYPE_LCD,
                struct.pack('>BBBB%ds' % len(text),
                cmd_defs.CMD_LCD_TEXT, row, col, len(text), bytes(text, 'ascii')))
        self._serial.write(cmd)
        self._get_resp()

    ## Turns on/off an LED.
    #
    # @param led is the LED number (LED1 [0] or LED2 [1]).
    # @param state is the requested LED state (0 - off, 1 - on).
    def led_set(self, led, state):
        if not led in [self.LED1, self.LED2]:
            raise Exception("Invalid LED number")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_LED,
                struct.pack('>BBB', cmd_defs.CMD_LED_SET, led, state))
        self._serial.write(cmd)
        self._get_resp()

    ## Keeps blinking an LED.
    #
    # @param led is the LED number (LED1 [0] or LED2 [1]).
    # @param period is the blinking period.
    def led_blink(self, led, period):
        if not led in [self.LED1, self.LED2]:
            raise Exception("Invalid LED number")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_LED,
                struct.pack('>BBB', cmd_defs.CMD_LED_BLINK, led, period))
        self._serial.write(cmd)
        self._get_resp()

    ## Returns the button state.
    #
    # Note that it is impossible to read 'left' button state, as it quits the
    # command interface mode.
    # @return Number indicating pressed buttons (BUT_RIGHT, BUT_DOWN, BUT_UP).
    def buttons(self):
        cmd = self._make_cmd(cmd_defs.CMD_TYPE_BTN)
        self._serial.write(cmd)
        return self._get_resp()[0]

    ## Reconfigures I2C clock frequency.
    #
    # The default I2C clock frequency is 100 kHz. It does not affect the
    # clock for the display data transfers (400 kHz).
    # @param clock_khz is the requested clock frequency [kHz, 1-400].
    def i2c_set_clock_khz(self, clock_khz):
        if clock_khz < 1 or clock_khz > 400:
            raise Exception("I2C clock must be in range [1-400] kHz")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_I2C,
                struct.pack('>BH', cmd_defs.CMD_I2C_CLOCK, clock_khz))
        self._serial.write(cmd)
        return self._get_resp()

    ## Reads registers over I2C.
    #
    # @param dev_addr is the 7-bit device address.
    # @param reg_addr is the register address.
    # @param length is number of bytes to read.
    # @return Registers contents.
    def i2c_read(self, dev_addr, reg_addr, length):
        if type(reg_addr) == int:
            reg_addr = reg_addr.to_bytes(max(1, (reg_addr.bit_length() + 7) // 8), 'big')

        reg_addr_len = len(reg_addr)

        if reg_addr_len > 4:
            raise Exception("I2C register address cannot be longer than 4 bytes")

        if length < 0 or length > 255:
            raise Exception("Requested data length must be in range [0-255]")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_I2C,
                struct.pack('>BBB%dsB' % (reg_addr_len),
                    cmd_defs.CMD_I2C_READ, dev_addr, reg_addr_len, reg_addr, length))
        self._serial.write(cmd)
        return self._get_resp()

    ## Writes registers over I2C.
    #
    # @param dev_addr is the 7-bit device address.
    # @param reg_addr is the register address.
    # @param data are the bytes to be written.
    def i2c_write(self, dev_addr, reg_addr, data):
        if type(reg_addr) == int:
            reg_addr = reg_addr.to_bytes(max(1, (reg_addr.bit_length() + 7) // 8), 'big')

        reg_addr_len = len(reg_addr)
        data_len = len(data)

        if reg_addr_len > 4:
            raise Exception("I2C register address cannot be longer than 4 bytes")

        if data_len > 255:
            raise Exception("Written data length must be in range [0-255]")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_I2C,
                struct.pack('>BBB%dsB%ds' % (reg_addr_len, data_len),
                    cmd_defs.CMD_I2C_WRITE, dev_addr, reg_addr_len, reg_addr, data_len, data))
        self._serial.write(cmd)
        self._get_resp()

    ## Configures the SPI peripheral.
    #
    # @param clock_khz is the clock frequency [1-60000 kHz].
    # @param mode is the SPI mode:
    #      0: capture data on rising clock edge, shift data on falling clock edge, inactive clock low
    #      1: capture data on falling clock edge, shift data on rising clock edge, inactive clock low
    #      2: capture data on falling clock edge, shift data on rising clock edge, inactive clock high
    #      3: capture data on rising clock edge, shift data on falling clock edge, inactive clock high
    def spi_config(self, clock_khz, mode):
        if clock_khz < 1 or clock_khz > 60000:
            raise Exception("SPI clock must be in range [1-60000] kHz")

        if mode < 0 or mode > 3:
            raise Exception("SPI mode must be in range [0-3]")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_SPI,
                struct.pack('>BHB', cmd_defs.CMD_SPI_CONFIG, clock_khz, mode))
        self._serial.write(cmd)
        self._get_resp()

    ## Transfers data over SPI. Uses PB14 (DAC1) as the active-low chip select.
    #
    # @param data_in are the bytes to be transferred.
    # @param returns received data.
    def spi_transfer(self, data_in):
        data_in_len = len(data_in)

        if data_in_len < 0 or data_in_len > 255:
            raise Exception("SPI data lenght must be in range [0-255]")

        cmd = self._make_cmd(cmd_defs.CMD_TYPE_SPI,
                struct.pack('>BB%ds' % data_in_len, cmd_defs.CMD_SPI_TRANSFER,
                    data_in_len, data_in))
        self._serial.write(cmd)
        return self._get_resp()
