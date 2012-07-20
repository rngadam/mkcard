# Create MicroSD card for Lophilo

Usage:

    sudo ./mkcard.py --dev /dev/sdb

## Pre-requisites:

* a OS image in $HOME/lophilo.nfs
* firmware binaries (with zImage and zImage-debug output from Lophilo Linux `makel firmware`) in $HOME/lophilo/upstream/firmware-binaries
* a 8GB MicroSD card (usually connected as a USB key using a USB adapter)


## known bug:

* unable to format a bootable DOS partition in Linux

Workaround, using a Windows machine: 

* backup files from DOS BOOT partition
* quick format dos partition
* copy files from backup 
