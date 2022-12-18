#! /bin/bash

sudo gpasswd -a $USER docker
newgrp docker
sudo systemctl start docker
