#!/usr/bin/env python

# sudo apt-get install python-parted
import _ped
import os
import code
import traceback 
import parted

class mkcardException(Exception):
	pass

LINUX_SWAP = _ped.file_system_type_get("linux-swap")
LINUX_NATIVE = _ped.file_system_type_get("ext4")
WINDOWS_FAT16 = _ped.file_system_type_get("fat16")

DISK_TYPE = _ped.disk_type_get("msdos")

if os.getenv("USER") != "root":
	raise mkcardException("Must be run as root")

try:
	device = parted.getDevice("/dev/sdc")
	disk = parted.Disk(device)
	for part in disk.partitions:
		print part
		# check if the partition are in use... if yes, abort
		if part.busy:
			raise mkcardException("Partition is busy" + part)

	# prompt user before wiping out disk...
	disk.deleteAllPartitions()
	disk.commitToDevice()
	disk.commitToOS()

	# create volatile store for new partition information

	# create fat, ext4 and swap partition
	start = 2048
	fat_length = 1026047
	ext4_length = 10000
	swap_length = 1000

 	disk = parted.freshDisk(device, DISK_TYPE)
 	constraint = parted.Constraint(device=device)
	geometry = parted.Geometry(device=device, start=start, end=fat_length)
	partition = parted.Partition(disk=disk, type=0, geometry=geometry)
	disk.addPartition(partition,constraint=constraint)
	partition.getPedPartition().set_system(WINDOWS_FAT16)
	#partition.getPedPartition().set_name("BOOT")
	
	geometry = parted.Geometry(device=device, start=partition.getLength(), length=ext4_length)
	partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geometry)
	disk.addPartition(partition,constraint=constraint)
	partition.getPedPartition().set_system(LINUX_NATIVE)	
	#partition.getPedPartition().set_name("os")

	geometry = parted.Geometry(device=device, start=partition.getLength(), length=swap_length)
	partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geometry)
	disk.addPartition(partition,constraint=constraint)
	partition.getPedPartition().set_system(LINUX_SWAP)		

	disk.commit()
except Exception as e:
	tb = traceback.format_exc()
	print tb
	code.interact(banner="", local=globals())