from enum import Enum
from monitorcontrol import get_monitors,  Monitor
import time
import libusb_package
from pydantic import BaseModel, Field
from typing import List, Set, Dict, Tuple
import usb.core
from usb.core import Device
import usb.backend.libusb1
import struct
import sys

class MonitorState(str, Enum):
    DP1 = 'DP1'
    DP2 = 'DP1'
    DP3 = 'DP1'
    HDMI1 = 'HDMI1'
    HDMI2 = 'HDMI2'
    HDMI3 = 'HDMI3'

class MonitorConfig(BaseModel):
    number: int
    name: str | None
    on_connect_state: MonitorState
    on_disconnect_state: MonitorState
    is_controllable: bool = True

class KVMConfig(BaseModel):
    usb_device: str
    enable_smart_switching: bool
    monitors: List[MonitorConfig]

class KVMException(Exception):
    def __init__(self, message):
        super().__init__(message)


libusb1_backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
WIN_PLATFORM = sys.platform == 'win32'
monitor_config_map: Dict[str, MonitorConfig] = {}
KVM_CONFIG = None

def is_usb_connected(device_id: str) -> bool:
    """ Check if a USB device is connected based on its ID in the format 'vendor_id:product_id' """
    vendor_id, product_id = device_id.split(':')
    connected  = usb.core.find(
        backend=libusb1_backend,
        idVendor=int(vendor_id),
        idProduct=int(product_id)
    )
    return connected is not None


def poll_if_monitor_controllable(monitor: Monitor) -> bool:
    """ Check if a monitor can be controlled by monitorcontrol. Return false if not. """
    with monitor:
        retry_count = 0
        while retry_count < 5:
            try:
                str(monitor.get_input_source()).split('.')[1]
                return True
            except Exception:
                retry_count += 1
                time.sleep(0.5)
    return False


def get_monitor_id(monitor: Monitor) -> str:
    if WIN_PLATFORM:
        return monitor.vcp.hmonitor.value  # transient value, changes any time devices are unplugged
    else:
        return monitor.vcp.bus_number 


def build_monitor_config_map():
    global monitor_config_map
    monitors = get_monitors()
    configs = KVM_CONFIG.monitors
    if len(monitors) != len(KVM_CONFIG.monitors):
        print('The number of connected monitors does not match the configured count. Retrying...')
        time.sleep(1)
        build_monitor_config_map()
    monitor_config_map = {}
    for monitor, config in zip(monitors, configs):
        monitor_id = get_monitor_id(monitor)
        controllable = poll_if_monitor_controllable(monitor)
        config.is_controllable = controllable
        monitor_config_map[monitor_id] = config


def get_config_for_monitor(monitor: Monitor) -> MonitorConfig | None:
    global monitor_config_map
    if monitor_config_map is None or len(monitor_config_map) == 0:
        build_monitor_config_map()
    monitor_id = get_monitor_id(monitor)
    return monitor_config_map.get(monitor_id, None)


def get_monitor_state(monitor: Monitor, monitor_config: MonitorConfig) -> MonitorState:
    """ Derives the provided monitor's MonitorState based on the configuration and current monitor state. """
    monitor_config.on_connect_state  # TODO use this to derive the current state that may not be input specific
    attempt_count = 0
    with monitor:
        while attempt_count < 20:
            try:
                state = str(monitor.get_input_source()).split('.')[1]
                state = MonitorState(state)
                print(f'Monitor {monitor_config.number} current state is: {state}')
                return state
            except struct.error as e:
                print(f'Error getting monitor state: {e}')
                time.sleep(0.5)
                attempt_count += 1
    raise KVMException(f'Error getting monitor state after {attempt_count} attempts')


def update_monitor_state(mon_config: MonitorConfig, monitor: Monitor, desired_state: MonitorState):
    """ Updates the provided monitor's state to match that of the desired_state MonitorState. """
    with monitor:
        print(f'Updating monitor {mon_config.number} state to {desired_state.value}')
        monitor.set_input_source(desired_state.value)


def handle_monitor_updates(usb_connected: bool):
    """
        Handles the monitor updates based  on the KVM config and whether the usb device is connected.
        If the monitor is uncontrollable by monitorcontrol, omit making any changes to its state.
        If the KVM config has smart switching enabled, monitor states will only be updated as necessary.
        Else, the monitor state will be forced to match the configred target state.
    """
    monitors: List[Monitor] = get_monitors()
    for monitor in monitors:
        config: MonitorConfig
        config = get_config_for_monitor(monitor)
        if config is None:
            build_monitor_config_map()
            handle_monitor_updates(usb_connected)
            return
        if not config.is_controllable:
            print(f'Monitor {config.number} cannot be controlled. Skipping updates...')
            continue
        desired_state = config.on_connect_state if usb_connected else config.on_disconnect_state
        if KVM_CONFIG.enable_smart_switching:
            current_state = get_monitor_state(monitor, config)
            if current_state != desired_state:
                print(current_state != desired_state)
                update_monitor_state(config, monitor, desired_state)
            continue
        update_monitor_state(config, monitor, desired_state)


def run_kvm(kvm_config: KVMConfig):
    """ Entrypoint into the KVM """
    kvm_config.monitors.sort(key=lambda m: m.number)
    global KVM_CONFIG
    KVM_CONFIG = kvm_config
    build_monitor_config_map()
    usb_connected = is_usb_connected(kvm_config.usb_device)
    handle_monitor_updates(usb_connected)
    time.sleep(1)
    while True:
        if usb_connected != is_usb_connected(kvm_config.usb_device):
            usb_connected = not usb_connected
            print(f"USB device {'connected ' if usb_connected else 'disconnected'}")
            handle_monitor_updates(usb_connected)


def print_connected_monitor_info():
    """
        Prints the information for each connected monitor, including model and possible inputs.
        If a monitor cannot be controlled by monitorcontrol, a warning message will be displayed for that monitor.
    """
    print("---------------Monitors---------------")
    for i, monitor in enumerate(get_monitors()):
        if not poll_if_monitor_controllable(monitor):
            print(f'Monitor {i}: Due to an unknown hardware or software issue, this monitor cannot be controlled via this program.')
            continue
        with monitor:
            capabilities = monitor.get_vcp_capabilities()
        monitor_name = capabilities['model']
        supported_inputs = [str(i).split('.')[1] for i in capabilities['inputs']]
        print(f'Monitor {i} ({monitor_name}): {supported_inputs}')

def get_connected_usb_devices() -> Set[Device]:
    """ Returns a set of the connected USB devices. """
    connected = usb.core.find(find_all=True, backend=libusb1_backend)
    return set(connected)


def try_get_string(dev: Device, index, langid = None, default_str_i0 = "Unknown", default_access_error = "Unknown"):
    """
        Attempt to get a string from the USB device metadata.
        If there is an error retrieving it, default to the provided value.
    """
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


def get_usb_device_info_string(device: Device):
    """ Return a summary of a USB device. """
    manufacturer = try_get_string(device, device.iManufacturer)
    dev_name = try_get_string(device, device.iProduct)
    return f"{device.idVendor}:{device.idProduct} ({manufacturer} {dev_name})"


def run_usb_identifier():
    """ 
        Run a USB identifier which prints all connected USB devices,
        then polls for added and removed devices to print.
    """
    print("---------------USB Devices------------")
    connected = get_connected_usb_devices()
    for c in connected:
        print(get_usb_device_info_string(c))
    print("--------------------------------------")
    print("\n\nRunning device finder -- press Ctrl+C to quit...")
    print("Plug in or unplug a device to view its ID...")
    try:
        while True:
            time.sleep(0.25)
            new_connected = get_connected_usb_devices()
            if connected != new_connected:
                removed = [get_usb_device_info_string(dev) for dev in (connected - new_connected)]
                added = [get_usb_device_info_string(dev) for dev in (new_connected - connected)]
                print(f"Connected: {added}    Disconnected: {removed}")
            connected = new_connected
    except KeyboardInterrupt:
        print("Exiting device finder")


def run_config_creator():
    """ Runs the initial setup config creator to create a config.json file for KVM configuration. """
    monitors = get_monitors()
    usb_device_id = input('Enter the USB device ID to monitor: ')
    print("--------------------------------------")
    print(f'Supported states are: {[state.value for state in MonitorState]}')
    monitor_configs: List[MonitorConfig] = []
    for i, monitor in enumerate(monitors):
        controllable = poll_if_monitor_controllable(monitor)
        monitor_name = 'Unknown'
        if controllable:
            with monitor:
                monitor_name = monitor.get_vcp_capabilities()['model']
        on_connect_state = MonitorState(input(f'Monitor {i} ({monitor_name}) on_connect state: '))
        on_disconnect_state = MonitorState(input(f'Monitor {i} ({monitor_name}) on_disconnect state: '))
        monitor_configs.append(MonitorConfig(
            number=i,
            name=monitor_name,
            on_connect_state=on_connect_state,
            on_disconnect_state=on_disconnect_state
        ))
    enable_smart = 'Y' == input('Would you like to enable smart state switching? (Y/N): ').upper()
    kvm_config = KVMConfig(
        usb_device=usb_device_id,
        enable_smart_switching=enable_smart,
        monitors=monitor_configs
    )
    with open('auto_config.json', 'w') as f:
        print(kvm_config.model_dump_json(indent=2), file=f)


def run_initial_setup():
    """ Runs the initial setup components to identify monitors, USB devices, and generate a new config file. """
    print('Building device list...')
    print_connected_monitor_info()
    run_usb_identifier()
    should_create_new_config = ("Y" == (input("Do you want to create a new config? (Y/N): ").upper()))
    if should_create_new_config:
        run_config_creator()


if __name__ == '__main__':
    # run_initial_setup()
    kvm_config: KVMConfig
    with open('auto_config.json', 'r') as f:
        config_text = f.read()
        kvm_config = KVMConfig.model_validate_json(config_text)
    try:
        run_kvm(kvm_config)
    except KVMException as e:
        print(f'An error occurred while running KVM: {e}. Exiting.')
    except Exception:
        run_kvm(kvm_config)


# if __name__ == "__main__":
#     parser = argparse.ArgumentParser()
#     parser.add_argument('-f', action='store_true', default=False, help='Use this flag to run the device finder to poll and print any changes in connected USB devices.')
#     parser.add_argument('-c', type=str, nargs='?', const="bar", default='config.json', help='Specify the config location. Else, default to config.json.')
#     parser.add_argument('-d', action='store_true', default=False, help='Use this flag to disable smart detection of current display inputs.')
#     parser.add_argument('-v', action='store_true', default=False, help='Use this flag to enable verbose logging of monitor sources when switching.')
#     args = parser.parse_args()
#     if args.f:
#         run_device_finder()
#     else:
#         config_location = args.c
#         dumb_mode = args.d
#         with open(config_location, 'r') as f:
#             kvm_config = json.load(f)
#         run_kvm(kvm_config, smart_mode_enabled=not dumb_mode, verbose=args.v)
