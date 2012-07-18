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

# doc for git
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

class mkcardException(Exception):
	pass


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

#TODO: calculate start/end or use constraints...
# configuration below assumes 8GB sd card...
partitions = [
	{
	'start': 2048,
	'end': 1044224,
	'type': _ped.file_system_type_get("fat16")
	},
	{
	'start': 1044225,
	'end': 14362109,
	'type': _ped.file_system_type_get("ext4")		
	},
	{
	'start': 14362110,
	'end': 15550919,
	'type': _ped.file_system_type_get("linux-swap")	
	}
]

# defaults
device_path = "/dev/sdc"
firmware_path = "/home/rngadam/lophilo/upstream/firmware-binaries"
os_path = "/home/rngadam/lophilo.nfs"
rsync_command = "rsync -avz --delete-delay --exclude-from excluded-files"
rsync_command_delete_excluded = "%s --delete-excluded" % rsync_command
target_rev = 'tabbyrev1'

# command-line parsing
parser = OptionParser()
parser.add_option(
	"-d", "--device", 
	action="store", type="string", dest="device_path",
	help="write report to FILE", metavar="DEVICE")

(options, args) = parser.parse_args()

if options.device_path is not None:
	device_path = options.device_path

if os.getenv("USER") != "root":
	raise mkcardException("Must be run as root")

def verify_partitions(device_path, partitions):
	device = parted.getDevice(device_path)
	disk = parted.Disk(device)
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

 	for partition in partitions:
		geometry = parted.Geometry(device=device, start=partition.start, end=partition.end)
		partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geometry)
		disk.addPartition(partition,constraint=constraint)
		partition.getPedPartition().set_system(partition.type)

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
	simple_call("%s %s/ %s/" % (rsync_command_delete_excluded, os_path, target_os_dir))

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

def force_umount(device_path):
	print "forcing umount of %s, ignore errors" % device_path
	os.system("pumount %s1" % (device_path))	
	os.system("pumount %s2" % (device_path))	

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
	if verify_partitions(device_path, partitions):
		print "partitions are OK"
	else:
		print "partitions don't match target, recreating"	
		create_partitions(device_path, partitions)
		format_disks(device_path)

	verify_repos(target_rev, [firmware_path, os_path])

	sync_os(device_path, firmware_path, os_path)

except Exception as e:
	tb = traceback.format_exc()
	print tb
	code.interact(banner="", local=globals())
