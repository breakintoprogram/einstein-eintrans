#!/usr/bin/python3

# Title:		EinTrans
# Author:		Dean Belfield
# Created:		05/02/2025
# Last Updated:	05/02/2025
#
# Modinfo:

import serial
import time

port = '/dev/ttyWCH0'

# Class to create a file object
#
class File:
	def __init__(self, buffer):
		filename = buffer[1:9].decode()
		extension = bytearray(b & 0x7F for b in buffer[9:12]).decode()
		self.filename = f"{filename}.{extension}" 
	
	def __repr__(self):
		return self.filename

# Class to wrap the serial port
#
class RS232:
	def __init__(self, port, baudrate, bytesize, parity, stopbits, timeout = None):
		self.serial = serial.Serial(port, baudrate, bytesize, parity, stopbits, timeout)

	def writeByte(self, b):
		self.write(bytes([b]))

	def write(self, data):
		while True:
			if self.serial.cts:
				break
		count = self.serial.write(data)
		time.sleep(0.001)
		return count 
	
	def read(self, size = None):
		return self.serial.read(size)
	
	def readByte(self):
		b = self.read(1)
		return b[0]
	
	def flush(self):
		self.serial.flush()

	def close(self):
		self.serial.close()

# Class to wrap the EinTrans protocol around the RS232 class
#
class Protocol(RS232):
	def __init__(self, port, baudrate, bytesize, parity, stopbits, timeout = None):
		super().__init__(port, baudrate, bytesize, parity, stopbits, timeout)

	# Send a command
	#
	def sendCmd(self, cmd, *args):
		self.flush()
		self.writeByte(0x2A)
		self.writeByte(0x21)
		self.writeByte(cmd)
		for item in args:
			self.writeByte(item)

	# Read buffer
	#
	def getBuffer(self, size):
		type = self.readByte()				# Get the type
		if type == 3:						# If type is 3 then
			value = self.readByte()			# Get the fill value
			return bytes([value])*size		# Return a buffer filled with that value
		elif type == 0:						# If type is 0 then
			data = self.read(size)			# Return the data
			rcs = self.readByte()			# Get the checksum
			tcs = sum(data)%0x100			# Our checksum
			self.writeByte(tcs)				# Return our checksum
			if tcs == rcs:					# If the checksums match
				return data					# Return the data
		return None							# In all other cases, return None

# Class to wrap the EinTrans functionality around the protocol
#
class Transfer(Protocol):
	def __init__(self, port, baudrate, bytesize, parity, stopbits, timeout = None):
		super().__init__(port, baudrate, bytesize, parity, stopbits, timeout)

	def reset(self):
		self.sendCmd(0x25)

	def setDisc(self, drive):
		self.sendCmd(0x53, drive)
		return self.readByte()
	
	def getDriveConfig(self):
		self.sendCmd(0x44)
		return self.readByte()
	
	def getDPB(self):
		self.sendCmd(0x42)
		dpb = self.getBuffer(15)
		return dpb
	
	def getDIR(self, drive):
		res = s.setDisc(drive)
		if res != 0:
			return None

		dir = []
		cfg = s.getDriveConfig()
		dpb = s.getDPB()
		entries = int.from_bytes(dpb[7:8]) + 1
		track = int.from_bytes(dpb[13:14])
		self.sendCmd(0x24, drive, track, entries >> 4)
		
		while True:
			result = self.readByte()
			if result == 0:
				buffer = self.getBuffer(0x10)
				if buffer[0] == 0:
					dir.append(File(buffer))
			else:
				break 

		return dir


# Configure serial port here. Last parameter is timeout to stop reading data, in seconds: 
#
s = Transfer(port, 9600, 8, "N", 2, 10)

drive = 0

result = s.reset()

dir = s.getDIR(drive)
print(dir)

s.close()