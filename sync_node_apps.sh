#!/bin/sh
DIRNAME=`dirname $0`
sudo mkdir -p /home/lophilo/local
sudo rsync -avz --delete-after --exclude-from $DIRNAME/excluded-files $HOME/lophilo/lmc /home/lophilo/local
if [ "$USER" != "lophilo" ]; then
	sudo chown -R lophilo:lophilo /home/lophilo/local
fi
