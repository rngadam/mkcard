#!/bin/sh
#
# Author: Ricky Ng-Adam <rngadam@lophilo.com>
# Lophilo Copyright 2012
#
# Sync current NFS root image to SD Card
#
# Assumptions:
# - executed from a booted Lophilo system
# - lophilo/ development directory is exported by host and mounted on lophilo (/media/BOOT/mount_lophilo.sh)
# - script is executed as ~/lophilo/mkcard/lophilo-sync.sh
#
DIR=`dirname $0`
sudo $DIR/mkcard.py \
	--dev /dev/mmcblk0 \
	--os / \
	--mount \
	--sync_os \
	--sync_firmware
