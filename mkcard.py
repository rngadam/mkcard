#!/usr/bin/env python

# sudo apt-get install python-parted
# sudo apt-get install python-git
# sudo apt-get install usbmount

# doc for parted:
# https://fedorahosted.org/pyparted/
# code examples:
# http://amebasystems.googlecode.com/svn-history/r233/research/a-i/stage-2/anaconda
# http://linux1.fnal.gov/linux/fermi/obsolete/lts309/x86_64/sites/Fermi/RHupdates/fsset.py
# http://magicinstaller2.googlecode.com/svn-history/r34/trunk/src/magic.installer/operations/parted.py

# doc for GitPython
# http://packages.python.org/GitPython/0.1/intro.html#getting-started

import _ped
import os
import code
import traceback 
import parted
import shutil
import git

from collections import OrderedDict
from subprocess import check_call
from optparse import OptionParser
from subprocess import Popen, PIPE

class mkcardException(Exception):
	pass


kcmd_default = OrderedDict({
	'mem': '128M',
	'ip': 'none',
	'noinitrd': None,
	'init': '/sbin/init',
	'rw': None,
	'root': '/dev/mmcblk0p2',
	'elevator': 'noop',
	'console': 'ttyS0',
	'rootwait': None
})

kcmd_nfs = OrderedDict({
	'root': '/dev/nfs',
	'ip': 'dhcp',
	'nfsroot': '10.42.0.1:/home/rngadam/lophilo.nfs',
	'nfsrootdebug': None,
	'rootwait': None,
	'rootfstype': 'nfs',
})

#TODO: calculate start/end or use constraints...
# configuration below assumes 8GB sd card...
#
# taken from this working config:
#
#   Device Boot      Start         End      Blocks   Id  System
#   /dev/sdb1   *          62     1998011      998975    b  W95 FAT32
#   /dev/sdb2         1998012    12483771     5242880   83  Linux
#   /dev/sdb3        12483772    15556607     1536418   82  Linux swap / Solaris

partitions = [
	{
	'start': 62,
	'end': 1998011,
	'type': _ped.file_system_type_get("fat32")
	},
	{
	'start': 1998012,
	'end': 12491387,
	'type': _ped.file_system_type_get("ext4")		
	},
	{
	'start': 12491388,
	'end': 15541787,
	'type': _ped.file_system_type_get("linux-swap")	
	}
]

# created with parted
#partitions = [
#	{
#	'start': 63,
#	'end': 1992059,
#	'type': _ped.file_system_type_get("fat32")
#	},
#	{
#	'start': 1992060,
#	'end': 12482504 ,
#	'type': _ped.file_system_type_get("ext4")		
#	},
#	{
#	'start': 12482505,
#	'end': 15550919 ,
#	'type': _ped.file_system_type_get("linux-swap")	
#	}
#]
# defaults
device_path = "/dev/sdb"
firmware_path = "%s/lophilo/upstream/firmware-binaries" % os.getenv("HOME")
os_path = "%s/lophilo.nfs" % os.getenv("HOME")
rsync_command = "rsync -avz --delete-delay --exclude-from excluded-files"
rsync_command_delete_excluded = "%s --delete-excluded" % rsync_command
target_rev = 'tabbyrev1'

# command-line parsing
parser = OptionParser()
parser.add_option(
	"-d", "--device", 
	action="store", type="string", dest="device_path",
	help="write report to FILE", metavar="DEVICE")
parser.add_option(
	"-f", "--firmware", 
	action="store", type="string", dest="firmware_path",
	help="source firmware directory", metavar="DIRECTORY")
parser.add_option(
	"-o", "--os", 
	action="store", type="string", dest="os_path",
	help="source OS directory", metavar="DIRECTORY")
parser.add_option("-s", "--skip_partition",
                  action="store_true", dest="skip_partition", default=False,
                  help="don't check and change partitions")
parser.add_option("-b", "--format_boot",
                  action="store_true", dest="format_boot", default=False,
                  help="force format boot partition")
parser.add_option("-m", "--format_os",
                  action="store_true", dest="format_os", default=False,
                  help="force format OS partition")
parser.add_option("-w", "--format_swap",
                  action="store_true", dest="format_swap", default=False,
                  help="force format SWAP partition")

(options, args) = parser.parse_args()

if options.device_path is not None:
	device_path = options.device_path
if options.firmware_path is not None:
	firmware_path = options.firmware_path
if options.os_path is not None:
	os_path = options.os_path

if os.getenv("USER") != "root":
	raise mkcardException("Must be run as root")

def verify_partitions(device_path, partitions):
	device = parted.getDevice(device_path)
	disk = parted.Disk(device)

	if len(partitions) != len(disk.partitions):
		print "partitions differ in length: desired %d current %d" % (len(partitions), len(disk.partitions))
		return False

	for part_id in xrange(0, len(partitions)):
		current_partition = disk.partitions[part_id]
		target_partition = partitions[part_id]
		
		current_partition_start = current_partition.getPedPartition().geom.start
		target_partition_start = target_partition['start']
		if current_partition_start != target_partition_start:
			print "start is not the same. current: %d target: %d" % (current_partition_start, target_partition_start)
			return False

		current_partition_end = current_partition.getPedPartition().geom.end
		target_partition_end = target_partition['end']
		if current_partition_end != target_partition_end:
			print "end is not the same. current: %d target: %d" % (current_partition_end, target_partition_end)
			return False

		# check if the partition are in use... if yes, abort
		if current_partition.busy:
			raise mkcardException("Partition is busy %s, please umount first" % current_partition)
	return True


def create_partitions(device_path, partitions):
	device = parted.getDevice(device_path)
	disk = parted.Disk(device)

	# prompt user before wiping out disk...
	disk.deleteAllPartitions()
	disk.commitToDevice()
	disk.commitToOS()

	# create volatile store for new partition information
	# create fat, ext4 and swap partition
 	disk = parted.freshDisk(device, _ped.disk_type_get("msdos"))

 	constraint = parted.Constraint(device=device)

 	for params in partitions:
		geometry = parted.Geometry(device=device, start=params['start'], end=params['end'])
		partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geometry)
		disk.addPartition(partition,constraint=constraint)
		partition.getPedPartition().set_system(params['type'])

	disk.commit()

def format_boot(device_path):
	print "FORMATTING BOOT (FAT32)"
	simple_call("dd if=/dev/zero of=%s1 bs=512 count=1" % (device_path))
	simple_call("mkdosfs -F 32 %s1 -n BOOT -v" % (device_path))

def format_os(device_path):
	print "FORMATTING EXT4"
	simple_call("mkfs.ext4 %s2 -L os -v" % (device_path))

def format_swap(device_path):
	print "FORMATTING SWAP"	
	simple_call("mkswap -L lplswap %s3" % (device_path))	

def simple_call(params):
	check_call(params.split(' '))

def sync_firmware(device_path, firmware_path):
	target_boot_dir = "/media/BOOT"
	# mount partitions created
	simple_call("pmount %s1 BOOT" % (device_path))	

	# now mounted as /media/BOOT
	simple_call("%s %s/ %s/" % (rsync_command, firmware_path, target_boot_dir))

	# git version 
	repo = git.Repo(firmware_path)
	file('%s/firmware.txt' % target_boot_dir, "w+").write(repo.git.describe("--always") + "\n")

	# write the kcmd references
	# there's a bug in one version of mboot that requires the string to be
	# aligned to 4 bytes. We append some spaces to prevent cutting the cmdline
	kcmd_default_str = create_cmd(kcmd_default) + "    "
	file('%s/kcmd_default.txt' % target_boot_dir, "w+").write(kcmd_default_str)
	kcmd_nfs_str = create_cmd(kcmd_default, kcmd_nfs) + "    "
	file('%s/kcmd_nfs.txt' % target_boot_dir, "w+").write(kcmd_nfs_str)
	kcmd_main_path = '%s/kcmd.txt' % target_boot_dir
	if os.path.isfile(kcmd_main_path):
		shutil.copy2(kcmd_main_path, '%s/kcmd.txt.bak' % target_boot_dir)	
	shutil.copy2('%s/kcmd_default.txt' % target_boot_dir, kcmd_main_path)	
	
	# umount all
	simple_call("pumount %s1" % (device_path))	

def sync_os(device_path, os_path):
	target_os_dir = "/media/os"
	# mount partitions created
	simple_call("pmount %s2 os" % (device_path))	

	# now mounted as /media/BOOT and /media/os
	simple_call("%s %s/ %s/" % (rsync_command_delete_excluded, os_path, target_os_dir))

	# slightly different configuration between
	# NFS boot and MicroSD card boot
	shutil.copy2('microsd-fstab', '%s/etc/fstab' % os_path)
	
	# umount all
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

def force_umount(device_path):
	print "forcing umount of %s, ignore errors" % device_path
	os.system("pumount %s1" % (device_path))	
	os.system("pumount %s2" % (device_path))	

def partition_copy(device_path):
	simple_call("dd if=/dev/zero of=%s bs=1024 count=1" % device_path)
	simple_call("dd if=partition-table of=%s bs=512 count=1" % device_path)

def boot_partition_copy(device_path):
	simple_call("dd if=dos-partition-extract of=%s1" % device_path)

def verify_repos(target_rev, repo_paths):
	for repo_path in repo_paths:
		repo = git.Repo(repo_path)
		if repo.active_branch != target_rev:
			raise mkcardException(
				'Expecting repo %s branch to match hardware rev %s (currently: %s)' % (
					repo, target_rev, repo.active_branch))
		else:
			print 'OK: repo %s active_branch is %s' % (repo, target_rev)

try:
	
	force_umount(device_path)

	if not options.skip_partition:
		if verify_partitions(device_path, partitions):
			print "partitions are OK"
		else:
			print "partitions don't match target, recreating"	
			create_partitions(device_path, partitions)
			options.format_boot = True
			options.format_os = True
			options.format_swap = True

	else:
		print "skipping partition check"
		
	if options.format_boot:
		format_boot(device_path)
	if options.format_os:
		format_os(device_path)
	if options.format_swap:
		format_swap(device_path)

	#verify_repos(target_rev, [firmware_path, os_path])

	sync_os(device_path, os_path)	
	sync_firmware(device_path, firmware_path)

except Exception as e:
	tb = traceback.format_exc()
	print tb
	code.interact(banner="", local=globals())
