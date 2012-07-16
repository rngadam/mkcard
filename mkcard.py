#!/usr/bin/env python

# sudo apt-get install python-parted

# doc:
# https://fedorahosted.org/pyparted/

# code examples:

# http://amebasystems.googlecode.com/svn-history/r233/research/a-i/stage-2/anaconda
# http://linux1.fnal.gov/linux/fermi/obsolete/lts309/x86_64/sites/Fermi/RHupdates/fsset.py
# http://magicinstaller2.googlecode.com/svn-history/r34/trunk/src/magic.installer/operations/parted.py

import _ped
import os
import code
import traceback 
import parted
import shutil
from collections import OrderedDict
from subprocess import check_call

class mkcardException(Exception):
	pass

LINUX_SWAP = _ped.file_system_type_get("linux-swap")
LINUX_NATIVE = _ped.file_system_type_get("ext4")
WINDOWS_FAT16 = _ped.file_system_type_get("fat16")

DISK_TYPE = _ped.disk_type_get("msdos")

kcmd_default = OrderedDict({
	'mem': '128M',
	'ip': 'dhcp',
	'noinitrd': None,
	'init': '/sbin/init',
	'rw': None,
	'root': '/dev/mmcblk0p2',
	'elevator': 'noop'
})

kcmd_nfs = OrderedDict({
	'root': '/dev/nfs',
	'nfsroot': '10.42.0.1:/home/rngadam/lophilo.nfs',
	'nfsrootdebug': None,
	'rootwait': None,
	'rootfstype': 'nfs',
})

device_path = "/dev/sdc"
firmware_path = "/home/rngadam/lophilo/upstream/firmware-binaries"
os_path = "/home/rngadam/lophilo.nfs"
rsync_command = "rsync -avz --delete-delay --delete-excluded --exclude-from excluded-files"

if os.getenv("USER") != "root":
	raise mkcardException("Must be run as root")

def create_partitions(device_path):

	device = parted.getDevice(device_path)
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

	#TODO: calculate start/end or use constraints...
	# configuration below assumes 8GB sd card...
	start = 2048
	fat_length = (512*1024*1024) / device.sectorSize
	swap_length = (512*1024*1024) / device.sectorSize
	ext4_length = device.length - (fat_length+swap_length+start)

	fat_start = 2048
	fat_end = 1050623

	ext4_start = 1050624
	ext4_end = 14362623

	swap_start = 14362624
	swap_end = 15556607

	# create volatile store for new partition information
	# create fat, ext4 and swap partition
 	disk = parted.freshDisk(device, DISK_TYPE)
 	constraint = parted.Constraint(device=device)

	geometry = parted.Geometry(device=device, start=fat_start, end=fat_end)
	partition = parted.Partition(disk=disk, type=0, geometry=geometry)
	disk.addPartition(partition,constraint=constraint)
	partition.getPedPartition().set_system(WINDOWS_FAT16)
	
	geometry = parted.Geometry(device=device, start=ext4_start, end=ext4_end)
	partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geometry)
	disk.addPartition(partition,constraint=constraint)
	partition.getPedPartition().set_system(LINUX_NATIVE)	

	geometry = parted.Geometry(device=device, start=swap_start, end=swap_end)
	partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geometry)
	disk.addPartition(partition,constraint=constraint)
	partition.getPedPartition().set_system(LINUX_SWAP)		

	disk.commit()

def format_disks(device_path):
	print "FORMATTING BOOT"
	simple_call("mkfs.msdos -F 16 %s1 -n BOOT -v" % (device_path))
	print "FORMATTING EXT4"
	simple_call("mkfs.ext4 %s2 -L os -v" % (device_path))
	print "FORMATTING SWAP"	
	simple_call("mkswap -L lplswap %s3" % (device_path))	

def simple_call(params):
	check_call(params.split(' '))

def sync_os(device_path, firmware_path, os_path):
	target_boot_dir = "/media/BOOT"
	target_os_dir = "/media/os"
	# mount partitions created
	simple_call("pmount %s1 BOOT" % (device_path))	
	simple_call("pmount %s2 os" % (device_path))	

	# now mounted as /media/BOOT and /media/os
	simple_call("%s %s/ %s/" % (rsync_command, firmware_path, target_boot_dir))
	simple_call("%s %s/ %s/" % (rsync_command, os_path, target_os_dir))

	# slightly different configuration between
	# NFS boot and MicroSD card boot
	shutil.copy2('microsd-fstab', '%s/etc/fstab' % os_path)

	# write the kcmd references
	file('%s/kcmd_default.txt' % target_boot_dir, "w+").write(create_cmd(kcmd_default))
	file('%s/kcmd_nfs.txt' % target_boot_dir, "w+").write(create_cmd(kcmd_default, kcmd_nfs))
	kcmd_main_path = '%s/kcmd.txt' % target_boot_dir
	if os.path.isfile(kcmd_main_path):
		shutil.copy2(kcmd_main_path, '%s/kcmd.txt.bak' % target_boot_dir)	
	shutil.copy2('%s/kcmd_default.txt' % target_boot_dir, kcmd_main_path)	
	
	# umount all
	simple_call("pumount %s1" % (device_path))	
	simple_call("pumount %s2" % (device_path))	

def create_cmd(kcmd, overrides=None):
	if overrides:
		for k in overrides:
			kcmd[k] = overrides[k]

	#parametrized value
	params = ['='.join([k, kcmd[k]]) for k in kcmd if kcmd[k]]
	# flag value
	params.extend([k for k in kcmd if not kcmd[k]])
	return ' '.join(params)

try:
	create_partitions(device_path)

	format_disks(device_path)

	sync_os(device_path, firmware_path, os_path)

except Exception as e:
	tb = traceback.format_exc()
	print tb
	code.interact(banner="", local=globals())