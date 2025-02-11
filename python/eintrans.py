#!/usr/bin/python3

# Title:		EinTrans
# Author:		Dean Belfield
# Created:		05/02/2025
# Last Updated:	11/02/2025
#
# Modinfo:
# 06/02/2025:	Added file transfer methods
# 11/02/2025	Fixed DIR statistics

import serial
import time
import math

port = '/dev/ttyWCH0'

# Class to create a DPB object
#
class DPB:
	def __init__(self, buffer):
		self.logicalSectorsPerTrack = buffer[0] + (buffer[6] << 1)
		self.blockShift = buffer[2]
		self.blockMask = buffer[3]
		self.blockingFlag = buffer[4]
		self.diskSize = buffer[5] + (buffer[6] << 8)
		self.directoryEntries = buffer[7] + (buffer[8] << 8) + 1
		self.allocMap = buffer[9] + (buffer[10] << 8)
		self.checkVector = buffer[11] + (buffer[12] << 8)
		self.systemTracks = buffer[13] + (buffer[14] << 8)
		self.blockSize = 128 << self.blockShift
		
	def getSize(self):
		return (self.diskSize + 1) * self.blockSize

# Class to create a file object
#
class File:
	def __init__(self, drive, buffer):
		self.drive = drive
		self.user = buffer[0]
		self.filename = buffer[1:9].decode().rstrip()
		self.extension = bytearray(b & 0x7F for b in buffer[9:12]).decode()
		self.readOnly = bool(buffer[9] & 0x80)
		self.hidden = bool(buffer[10] & 0x80)
		self.archived = bool(buffer[11] & 0x80)
		self.size = buffer[15] * 128
	
	def __repr__(self):
		return f"{self.drive}:{self.filename}.{self.extension} [{self.size}]"

# Class to represent a directory
#
class Dir:
	def __init__(self):
		self.drive = None
		self.driveConfig = None 
		self.dpb = None 
		self.entries = []
		self.__used = 0

	def findFile(self, drive, filename, extension):
		for file in self.entries:
			if file.drive == drive and file.filename == filename and file.extension == extension:
				return file
		return None			

	def append(self, drive, file):
		blockSize = self.dpb.blockSize
		self.__used += math.ceil(file.size / blockSize) * blockSize
		f = self.findFile(drive, file.filename, file.extension)
		if f == None:
			self.entries.append(file)
		else:
			f.size += file.size

	def used(self):
		return self.__used

	def free(self):
		return self.total() - self.used()

	def total(self):
		if self.dpb != None:
			return self.dpb.getSize()
		return 0

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
		self.writeByte(0x2A)
		self.writeByte(0x21)
		self.writeByte(cmd)
		for item in args:
			self.writeByte(item)

	# Send a string
	#
	def sendStr(self, string):
		for char in string:
			self.writeByte(ord(char))

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
	
	# Send buffer
	# 
	def sendBuffer(self, buffer):
		self.writeByte(0)					# Flag we are not filling
		self.write(buffer)					# Write out the buffer
		rcs = self.readByte()				# Get the checksum
		tcs = sum(buffer)%0x100				# Our checksum
		self.writeByte(tcs)					# Return our checksum
		return tcs == rcs

	# Fill buffer
	#
	def fillBuffer(self, byte):
		self.writeByte(3)		
		self.writeByte(byte)				# Byte to fill buffer with, count determined by Einstein

# Class to wrap the EinTrans functionality around the protocol
#
class Transfer(Protocol):
	def __init__(self, port):
		super().__init__(port, 9600, 8, "N", 2, 10)

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
		buffer = self.getBuffer(15)
		return DPB(buffer)
	
	def getDIR(self, drive):
		dir = Dir()
		res = self.setDisc(drive)
		if res != 0:
			return dir
		dir.drive = drive
		dir.dpb = self.getDPB()
		dir.driveConfig = s.getDriveConfig()
		self.sendCmd(0x24, drive, dir.dpb.systemTracks, dir.dpb.directoryEntries >> 4)		
		while True:
			result = self.readByte()
			if result == 0:
				buffer = self.getBuffer(0x10)
				if buffer[0] == 0:
					dir.append(drive, File(drive, buffer))
			else:
				break 
		return dir
	
	def getFile(self, drive, filename, extension):
		self.sendCmd(0x52)
		self.sendStr(f"{drive}{filename.ljust(8)}{extension}")
		res = self.readByte()
		if res != 0:
			return None 
		fh = open(f"{filename}.{extension}", 'wb')		
		while True:
			res = self.readByte()
			if res != 0:
				break 
			buffer = self.getBuffer(0x80)
			fh.write(buffer)
		fh.close()
		return res
	
	def putFile(self, drive, filename, extension):
		fh = open(f"{filename}.{extension}", 'rb')
		self.sendCmd(0x57)
		self.sendStr(f"{drive}{filename.ljust(8)}{extension}")
		res = self.readByte()
		if res != 0:
			return None
		while True:
			buffer = fh.read(0x80)
			self.sendBuffer(buffer.ljust(0x80, b"\0"))
			res = self.readByte()
			if len(buffer) < 0x80:
				self.writeByte(2)
				break
			else:
				self.writeByte(0)
		fh.close()
		return res
	
# Test code
#
s = Transfer(port)	# Open the serial port

res = s.reset()		# Send a reset command to EinTrans
dir = s.getDIR(0)	# Get the directory

# Iterate through the directory and get the files from the Einstein
#
for file in dir.entries:
	print(f"{file.drive}:{file.filename}.{file.extension} = {file.size}")
print(f"{dir.used() // 1024}K Size, {dir.free() // 1024}K Free, {dir.total() // 1024}K Total")

s.close()			# Close the serial port
