# USB-KVM
Turn an ordinary USB Switch into a full KVM by polling and monitoring USB connect/disconnect events and sending DDC/CI signals to switch display input according to a configuration file.

## Installation
```sh
git clone https://github.com/joermo/usb-kvm.git
cd usb-kvm
python3 -m venv ./venv
source ./venv/bin/activate
pip install -r requirements.txt
```
This script requires read/write access to `/dev/i2c` devices. If you're on linux, proceed with creating a new group and assigning to yourself by following the below instructions. Else you can run the script as root, or assign temporary access via `sudo chmod a+rw /dev/i2c-*`.
```
sudo groupadd i2c
sudo chown :i2c /dev/i2c-*
sudo chmod g+rw /dev/i2c-*
whoami | xargs sudo usermod -aG i2c
sudo -i
echo 'KERNEL=="i2c-[0-9]*", GROUP="i2c"' >> /etc/udev/rules.d/10-local_i2c_group.rules
```

## Configuration
KVM is configured via the following configuration structure:
```json
{
    "usb_device": "6048:772",
    "monitors": {
        "1": {
            "on_connect_input": "DP1",
            "on_disconnect_input": "HDMI1"
        },
        "2": {
            "on_connect_input": "DP1",
            "on_disconnect_input": "HDMI2"
        }
    }
}
```
- `usb_device` is the USB device ID that is polled intermittently to update the connected monitors depending on its connected status.
- `monitors` represents the list of monitors connected/to be updated by the script
- `on_connect_input` is the monitor input to use when the USB device is `connected` to the host
- `on_disconnect_input` is the monitor input to use when the USB device is `NOT connected` to the host

The monitors must be in order that the script setup detects them in. For more information, see `-f` in the arguments section.


## Arguments
```
-h  :   Display argument help
-f  :   Run KVM in device finder/setup mode. Follow the displayed prompts to complete initial setup and create KVM config file.
-d  :   Enable compatibility 'dumb monitor' flag. Some monitors will not properly display the currently used input option over DDC/CI, so logic based on the current input selection cannot be leveraged. Hence, this will ensure the correct input selection is set. Will cause initial screen flicker upon startup.
-c  :   Specify the KVM config directory. If not provided, use ./config.json.
-v  :   Use this flag to enable verbose logging of monitor sources when switching.
```

- Using `-f` for initial configuration to remove any annoying guesswork is highly encouraged.
- If monitor inputs only switch once and won't switch back, try using the `-d` flag alongside `-v`.

## Running script directly
python3 kvm.py

## Packaging script into executable
Some may find it helpful to package USB-KVM into a standalone executable for ease of running. Do so via the following:
```
pip install pyinstaller
pyinstaller --onefile kvm.py
```
