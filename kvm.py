# pip install monitorcontrol
# pip install pyusb
# pip install libusb-package

# Package into single executable:
# pip install pyinstaller
# pyinstaller --onefile kvm.py

from monitorcontrol import get_monitors
import time
import libusb_package
import usb.core
import usb.backend.libusb1
import json
import argparse
import os


def is_usb_connected(device_id):
    ven_prod = device_id.split(':')
    vendor_id = int(ven_prod[0])
    prod_id = int(ven_prod[1])
    libusb1_backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
    connected = usb.core.find(find_all=True, backend=libusb1_backend)
    for c in connected:
        if c.idVendor == vendor_id and c.idProduct == prod_id:
            return True
    return False


def switch_monitor_inputs(config, is_connected, smart_mode_enabled, log_source):
    monitors = config['monitors']
    for i, monitor in enumerate(get_monitors()):
        with monitor:
            input_to_set = monitors[str(i + 1)]["on_connect_input"] if is_connected else monitors[str(i + 1)]["on_disconnect_input"]
            current_source = str(monitor.get_input_source()).split('.')[1] # get last part of enum
            if log_source:
                print(f"Monitor {i + 1} current source: {current_source}")
            if smart_mode_enabled:
                if current_source == input_to_set:
                    print(f"Monitor {str(i + 1)} already set to input {input_to_set}")
                else:
                    print(f"Setting display {i + 1} to {input_to_set}")
                    monitor.set_input_source(input_to_set)
            else:
                print(f"Setting display {i + 1} to {input_to_set}")
                monitor.set_input_source(input_to_set)


def get_connected_devices():
    libusb1_backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
    connected = usb.core.find(find_all=True, backend=libusb1_backend)
    return set(connected)


def try_get_string(dev, index, langid = None, default_str_i0 = "Unknown", default_access_error = "Unknown"):
    if index == 0 :
        string = default_str_i0
    else:
        try:
            if langid is None:
                string = usb.util.get_string(dev, index)
            else:
                string = usb.util.get_string(dev, index, langid)
        except Exception:
            string = default_access_error
    return string

    
def get_device_info(device):
    manufacturer = try_get_string(device, device.iManufacturer)
    dev_name = try_get_string(device, device.iProduct)
    return f"{device.idVendor}:{device.idProduct} ({manufacturer} {dev_name})"


def create_config(monitors):
    config = {}
    device_id = input("Enter the USB device ID: ")
    config['usb_device'] = device_id
    config['monitors'] = {}
    for mon_num, mon_name in monitors.items():
        print("--------------------------------------")
        print(f"Monitor {mon_num} {mon_name}:")
        on_connect = input("on_connect input: ")
        on_disconnect = input("on_disconnect input: ")
        config['monitors'][mon_num] = {"on_connect_input": on_connect, "on_disconnect_input": on_disconnect}
    config_json = json.dumps(config, indent = 4) 
    with open('config.json', 'w') as f:
        print(config_json, file=f)
    print(f"Config file output to: {os.getcwd()}")


def run_device_finder():
    print(f"Building device list...")
    print("---------------Monitors---------------")
    monitors = {}
    for i, monitor in enumerate(get_monitors()):
        with monitor:
            inputs = [str(i).split('.')[1] for i in monitor.get_vcp_capabilities()['inputs']]
            monitors[i+1] = f"{monitor.get_vcp_capabilities()['model']} {inputs}"
            print(f"Monitor {i+1}: {monitors[i+1]}")
    connected = get_connected_devices()
    print("---------------USB Devices------------")
    for c in connected:
        print(get_device_info(c))
    print("--------------------------------------")
    print("\n\nRunning device finder -- press Ctrl+C to quit...")
    print(f"Plug in or unplug a device to view its ID...")
    try:
        while True:
            time.sleep(0.25)
            new_connected = get_connected_devices()
            if connected != new_connected:
                removed = [f"{r.idVendor}:{r.idProduct}" for r in (connected - new_connected)]
                added = [f"{a.idVendor}:{a.idProduct}" for a in (new_connected - connected)]
                print(f"Connected: {added}    Disconnected: {removed}")
            connected = new_connected
    except KeyboardInterrupt:
        print("Exiting device finder")
    
    to_create_config = ("Y" == (input("Do you want to create a new config? (Y/N): ").upper()))
    if to_create_config:
        create_config(monitors)


def run_kvm(config, smart_mode_enabled, verbose):
    usb_id = config['usb_device']
    is_connected = is_usb_connected(usb_id)
    if is_connected:
        print(f'Device {usb_id} is connected')
    else:
        print(f'Device {usb_id} is not connected')
    switch_monitor_inputs(config, is_connected, smart_mode_enabled, verbose)
    while True:
        is_connected_new = is_usb_connected(usb_id)
        if is_connected != is_connected_new:
            print("USB device switched")
            switch_monitor_inputs(config, is_connected_new, smart_mode_enabled, verbose)
            is_connected = is_connected_new
        time.sleep(.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', action='store_true', default=False, help='Use this flag to run the device finder to poll and print any changes in connected USB devices.')
    parser.add_argument('-c', type=str, nargs='?', const="bar", default='config.json', help='Specify the config location. Else, default to config.json.')
    parser.add_argument('-d', action='store_true', default=False, help='Use this flag to disable smart detection of current display inputs.')
    parser.add_argument('-v', action='store_true', default=False, help='Use this flag to enable verbose logging of monitor sources when switching.')
    args = parser.parse_args()
    if args.f:
        run_device_finder()
    else:
        config_location = args.c
        dumb_mode = args.d
        with open(config_location, 'r') as f:
            kvm_config = json.load(f)
        run_kvm(kvm_config, smart_mode_enabled=not dumb_mode, verbose=args.v)
