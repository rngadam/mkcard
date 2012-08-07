#!/usr/bin/env python

# sudo apt-get install python-parted
# sudo apt-get install python-git

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
import sys

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

partitions = [
    {
    'length': 128,
    'type': "fat32"
    },
    {
    'type': "ext4"
    },
    {
    'length': 1024,
    'type': "linux-swap"
    }
]


if os.getenv("USER") != "root":
    raise mkcardException("Must be run as root")

basedir = sys.path[0]

# defaults
rsync_command_os = (
    "rsync -avzx --delete-delay --exclude-from"
    " %s/excluded-files --delete-excluded" % basedir)
rsync_command_firmware = (
    "rsync -vdrzx --delete-delay"
    " --exclude-from %s/excluded-files" % basedir)

target_rev = 'tabbyrev1'

# command-line parsing
parser = OptionParser()

# PARAMETERS
parser.add_option("-d", "--device", 
                  action="store", type="string", dest="device_path",
                  help="use DEVICE", metavar="DEVICE",
                  default="/dev/sdb")
parser.add_option("-f", "--firmware", action="store", 
                  type="string", dest="source_firmware_path",
                  help="source firmware directory", metavar="DIRECTORY",
                  default="%s/lophilo/firmware-binaries" % os.getenv("HOME"))
parser.add_option("-u", "--target_firmware", 
                  action="store", type="string", dest="target_firmware_path",
                  help="target OS directory", metavar="DIRECTORY",
                  default="/media/BOOT")
parser.add_option("-o", "--os", 
                  action="store", type="string", dest="source_os_path",
                  help="source OS directory", metavar="DIRECTORY",
                  default="%s/lophilo.nfs" % os.getenv("HOME"))
parser.add_option("-t", "--target_os", action="store", 
                  type="string", dest="target_os_path",
                  help="target firmware directory", metavar="DIRECTORY",
                  default="/media/os")

# ACTIONS
parser.add_option("-c", "--create_partition",
                  action="store_true", dest="create_partition", 
                  help="check and change partitions",
                  default=False)
parser.add_option("-b", "--format_boot",
                  action="store_true", dest="format_boot",
                  help="force format boot partition",
                  default=False)
parser.add_option("-m", "--format_os",
                  action="store_true", dest="format_os", 
                  help="force format OS partition",
                  default=False)
parser.add_option("-w", "--format_swap",
                  action="store_true", dest="format_swap",
                  help="force format SWAP partition", 
                  default=False)
parser.add_option("-n", "--mount",
                  action="store_true", dest="mount", 
                  help="mount partitions to filesystem",
                  default=False,)
parser.add_option("-a", "--sync_os",
                  action="store_true", dest="sync_os", 
                  help="sync OS filesystem",
                  default=False,)
parser.add_option("-z", "--sync_firmware",
                  action="store_true", dest="sync_firmware", 
                  help="sync firmware filesystem",
                  default=False)

(options, args) = parser.parse_args()


def verify_partitions(device_path, partitions):
    device = parted.getDevice(device_path)
    disk = parted.Disk(device)

    if len(partitions) != len(disk.partitions):
        print "partitions differ in length: desired %d current %d" % (len(partitions), len(disk.partitions))
        return False

    for part_id in xrange(0, len(partitions)):
        current_partition = disk.partitions[part_id]
        target_partition = partitions[part_id]        

        # check filesystem type
        if not current_partition.fileSystem:
            # no filesystem...
            return False

        current_fs_type = current_partition.fileSystem.getPedFileSystem().type.name
        if current_fs_type != target_partition['type']:
            print "partition type does not match: expected %s, got %s" % (target_partition['type'], current_fs_type)
            return False

        # check if the partition are in use... if yes, abort
        if current_partition.busy:
            raise mkcardException("Partition is busy %s, please umount first" % current_partition)

    return True


def mb_to_sector(disk, mb):
    return  (mb*1024*1024)/disk.device.sectorSize

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
    max_length_sectors = disk.device.getLength()
    fat32_size = mb_to_sector(disk, partitions[0]['length'])
    swap_size = mb_to_sector(disk, partitions[2]['length'])
    ext4_size = max_length_sectors - (fat32_size+swap_size)
    fat32_geom = parted.Geometry(device=device, start=0, length=fat32_size)
    ext4_geom = parted.Geometry(device=device, start=fat32_size, length=ext4_size)
    swap_geom = parted.Geometry(device=device, start=ext4_size+fat32_size, length=swap_size)
    for part_type, geom in [("fat32", fat32_geom), ("ext4", ext4_geom), ("linux-swap", swap_geom)]:
        print "creating %s with geom: %s" % (part_type, geom)
        partition = parted.Partition(disk=disk, type=parted.PARTITION_NORMAL, geometry=geom)
        disk.addPartition(partition,constraint=constraint)
        part_type_ped = _ped.file_system_type_get(part_type)
        partition.getPedPartition().set_system(part_type_ped)
    disk.commitToDevice()
    disk.commitToOS()        

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
    print "executing: %s" % params
    check_call(params.split(' '))

def sync_firmware(source_firmware_path, target_firmware_path):
    assert os.path.ismount(target_firmware_path)
    simple_call("%s %s/ %s/" % (rsync_command_firmware, source_firmware_path, target_firmware_path))

    # git version 
    file('%s/firmware.txt' % target_firmware_path, "w+").write(get_git_version(source_firmware_path))

    # write the kcmd references
    # there's a bug in one version of mboot that requires the string to be
    # aligned to 4 bytes. We append some spaces to prevent cutting the cmdline
    kcmd_default_str = create_cmd(kcmd_default) + "    "
    file('%s/kcmd_default.txt' % target_firmware_path, "w+").write(kcmd_default_str)
    kcmd_nfs_str = create_cmd(kcmd_default, kcmd_nfs) + "    "
    file('%s/kcmd_nfs.txt' % target_firmware_path, "w+").write(kcmd_nfs_str)
    kcmd_main_path = '%s/kcmd.txt' % target_firmware_path
    if os.path.isfile(kcmd_main_path):
        shutil.copy2(kcmd_main_path, '%s/kcmd.txt.bak' % target_firmware_path)  
    shutil.copy2('%s/kcmd_default.txt' % target_firmware_path, kcmd_main_path)      

def mount_partition(device_path, target_dir):
    assert not os.path.ismount(target_dir)
    if not os.path.exists(target_dir):
        print "creating %s" % target_dir
        os.makedirs(target_dir)
    simple_call("mount %s %s" % (device_path, target_dir))  

def umount_partition(target_dir):
    simple_call("umount %s" % (target_dir)) 
    if os.path.exists(target_dir):
        print "removing %s" % target_dir        
        os.rmdir(target_dir)

def get_git_version(git_path):
    repo = git.Repo(git_path)
    return repo.git.describe("--always") + "\n"

def sync_os(source_os_path, target_os_path):
    assert os.path.ismount(target_os_path)
    simple_call("%s %s/ %s/" % (rsync_command_os, source_os_path, target_os_path))

    # slightly different configuration between
    # NFS boot and MicroSD card boot: we don't mount OS partition with SD boot
    shutil.copy2('%s/microsd-fstab' % basedir, '%s/etc/fstab' % target_os_path)

    # keep track of version
    file('%s/etc/lophilo_version' % target_os_path, "w+").write(get_git_version(source_os_path))
    
    # fix incorrect extendend permissions introduced by git
    simple_call("chmod a+s %s/usr/bin/sudo" % target_os_path)
    simple_call("chmod 0440 %s/etc/sudoers" % target_os_path)
    simple_call("chmod 0440 %s/etc/sudoers.d/README" % target_os_path)

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
    os.system("umount %s" % (device_path))   

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
    
    if options.mount:
        print "UN-mounting devices"
        force_umount(options.device_path + '1')
        force_umount(options.device_path + '2')

    if options.create_partition:
        if verify_partitions(options.device_path, partitions):
            print "partitions are OK"
        else:
            print "partitions don't match target, recreating"   
            create_partitions(options.device_path, partitions)

    else:
        print "skipping partition check"
        
    if options.format_boot:
        print "re-UN-mounting devices (gets remounted by system)"
        force_umount(options.device_path + '1')
        format_boot(options.device_path)
    else:
        print "not formatting boot partition"
    if options.format_os:
        format_os(options.device_path)
    else:
        print "not formatting os partition"

    if options.format_swap:
        format_swap(options.device_path)
    else:
        print "not formatting swap partition"       

    #verify_repos(target_rev, [source_firmware_path, source_os_path])
    if options.mount:
        print "mounting devices"
        mount_partition('%s1' % options.device_path, '/media/BOOT')
        mount_partition('%s2' % options.device_path, '/media/os')
    else:
        print "skipping mount"

    if options.sync_os:
        print "syncing OS filesystem"
        sync_os(options.source_os_path, options.target_os_path) 
    else:
        print "not syncing OS filesystem"

    if options.sync_firmware:
        print "syncing firmware filesystem"
        sync_firmware(options.source_firmware_path, options.target_firmware_path)
    else:
        print "not syncing firwmare filesystem"

    if options.mount:
        print "UN-mounting devices"
        umount_partition('/media/os')
        umount_partition('/media/BOOT') 
    else:
        print "skipping umount"

except Exception as e:
    print traceback.format_exc()
    from pdb import set_trace; set_trace()

