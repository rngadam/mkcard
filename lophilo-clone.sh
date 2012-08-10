#!/bin/sh
#
# Author: Ricky Ng-Adam <rngadam@lophilo.com>
# Lophilo Copyright 2012
#
# create bootable sdcard cloning from current booted SD card or 
# nfs drive to auxiliary card (/dev/mmcblk1)
#
# we clone the FAT32 partition #1 because mkdosfs results in
# an unbootable filesystem
#
# Assumptions:
# - executed from a booted Lophilo system
# - current FAT32 boot partition size is same size as target
# - lophilo/ development directory is exported by host and mounted on lophilo (/media/BOOT/mount_lophilo.sh)
# - script is executed as ~/lophilo/mkcard/lophilo-clone.sh
# - there's a MicroSD card in the auxiliary port
#
DIR=`dirname $0`
sudo $DIR/mkcard.py \
	--dev /dev/mmcblk1 \
	--os / \
	--clone_boot_source /dev/mmcblk0p1 \
	--mount \
	--create_partition \
	--clone_boot \
	--format_os \
	--format_swap \
	--sync_os \
	--sync_firmware
