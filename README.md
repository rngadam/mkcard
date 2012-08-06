# Create MicroSD card for Lophilo

Dependencies:

  sudo apt-get install python-parted python-git

Usage:

Make sure to specify the device with --dev. Examples below use the default (/dev/sdb). 

You may also want to specify the firmware source (--firmware) and os source directory (--os).

Creating partitions and formatting them:

    sudo ./mkcard.py --create_partition --format_boot --format_os --format_swap

Mounting disks, syncing data partitions and umounting:

    sudo ./mkcard.py --mount --sync_os --sync_firmware

Complete creation from scratch:

	sudo ./mkcard.py --mount --dev /dev/sdb --create_partition --format_boot --format_os --format_swap --sync_os --sync_firmware
	
Updating from a running Lophilo using a exported NFS drive with Lophilo OS on it (make sure that the files after with the right permissions):

	# mount -t nfs -o all_no_squash 10.42.0.1:/home/rngadam/lophilo.nfs lophilo.nfs   
	# ~/lophilo/mkcard/mkcard.py --sync_os --target_os /

## Pre-requisites:

* a OS image in $HOME/lophilo.nfs (make sure the Linux kernel modules are setup to match the kernel version in firmware-binaries with `makel setup-nfs-dir`)
* firmware binaries (with zImage and zImage-debug output from Lophilo Linux `makel firmware`) in $HOME/lophilo/upstream/firmware-binaries
* a 8GB MicroSD card (usually connected as a USB key using a USB adapter); make sure you find out the correct device! destroying partitions and formatting is irretrievable!

## known bug:

* unable to format a bootable DOS partition in Linux

Workaround, using a Windows machine: 

* backup files from DOS BOOT partition
* quick format dos partition
* copy files from backup 
