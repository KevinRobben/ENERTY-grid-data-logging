# ENERTY-grid-data-logging
log Module-M grid data as well as modbus energy meter data from an RBPi to supabase
WARNING: This is not a public effort! WE will not accept pull requests. The supabase database is NOT open source. 
This project builds uppon the Enerty-Module-M energy meter, to verify its data with a modbus energy meter.


# activate virtual enviroment
(first install: python3 -m venv myenv)
chmod +x venv_acitvate.sh
./venv_acitvate.sh


# manual firmware update
active the virtual enviroment

make sure that "github_token" is added to user_data.yaml
on linux run python ./manual_update_firmware.py "https://github.com/KevinRobben/ENERTY-Module-M/blob/main/dist/flash_esp32s2_V2.0.6.uf2"

change the link to the uf2 file that you want to upload.
on windows run python ./manual_update_firmware.py "https://github.com/KevinRobben/ENERTY-Module-M/blob/main/dist/flash_esp32s2_V2.0.6.uf2"


on linux if you get 
bash ```
M/blob/main/dist/flash_esp32s2_V2.0.6.uf2"
/usr/bin/env: ‘python3\r’: No such file or directory
/usr/bin/env: use -[v]S to pass options in shebang lines
```
run dos2unix manual_update_firmware.py

If dos2unix is not installed, install it first:
sudo apt update
sudo apt install dos2unix


# setup a new rbpi
- Get a rbpi 4
- Install pios lite 64 bit
- Install git: sudo apt install git-all
- Install tailscale: https://tailscale.com/kb/1174/install-debian-bookworm
- Enable tailscale Auto-Start on Boot: sudo systemctl enable tailscaled
- Enable remote ssh from browser and vscode: tailscale set --ssh
- Install pip: sudo apt-get update and sudo apt-get install python-pip
- clone this repo:  git clone https://github.com/KevinRobben/ENERTY-grid-data-logging.git
- set username and email:
    git config --global user.name "GITHUB USERNAME" 
    git config --global user.email "GITHUM EMAIL"