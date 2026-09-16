"""
Headless entry point for ShadowLink.
Loads the active profile and runs the controller sniffer loop with real-time console logging
to verify back paddle presses (M1-M4, Command, Library) and combos.
"""

from __future__ import annotations
import argparse
import logging
import signal
import sys
import time
from typing import NoReturn

import config
import hardware
from models import DeviceStatus, Profile

# Configure standard console logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ShadowLink.Headless")


def print_banner(profile: Profile) -> None:
    print("=" * 64, flush=True)
    print("  ShadowLink - ASUS ROG Controller Paddle Sniffer (Headless)", flush=True)
    print(f"  Active Profile: {profile.name}", flush=True)
    print(f"  Target Process: {profile.target_process or '(None)'}", flush=True)
    print(f"  Combo Buffer:   {profile.combo_buffer_ms} ms", flush=True)
    print(f"  Toggle Buttons: {profile.toggle_button1} + {profile.toggle_button2}", flush=True)
    print(f"  Layers ({len(profile.layers)} configured):", flush=True)
    for i, layer in enumerate(profile.layers):
        status = "ENABLED" if layer.enabled else "disabled"
        print(f"    [{i+1}] {layer.name:<15} ({status})", flush=True)
    print("=" * 64, flush=True)
    print("Listening for back paddle presses (Ctrl+C to stop)...\n", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="ShadowLink Headless Paddle Sniffer")
    parser.add_argument(
        "--profile", "-p",
        type=str,
        default=None,
        help="Name of the profile to load (defaults to active profile in config.json or 'Default')"
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable verbose DEBUG logging"
    )
    parser.add_argument(
        "--list-devices", "-l",
        action="store_true",
        help="List all detected ASUS HID devices and exit"
    )

    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.list_devices:
        devices = hardware.find_raikiri_hid_devices()
        print(f"\nFound {len(devices)} ASUS HID devices:")
        for idx, dev in enumerate(devices):
            up = dev.get("usage_page", 0)
            is_paddle = hardware.is_raikiri_paddle_device(dev)
            print(f"  [{idx+1}] {dev.get('product_string', 'Unknown')}")
            print(f"      VID: 0x{dev.get('vendor_id', 0):04X}, PID: 0x{dev.get('product_id', 0):04X}")
            print(f"      UsagePage: 0x{up:04X} ({hex(up)}) -> Raikiri Paddle Interface: {is_paddle}")
            print(f"      Path: {dev.get('path', b'')}")
        return

    # Load profiles & global configuration
    global_cfg = config.load_global_config()
    all_profiles = config.load_all_profiles()

    target_name = args.profile or global_cfg.get("active_profile", "Default")
    selected_profile = next((p for p in all_profiles if p.name.lower() == target_name.lower()), all_profiles[0])

    print_banner(selected_profile)

    manager = hardware.ControllerManager(selected_profile)

    # Setup callbacks for live feedback
    def on_paddle(name: str, raw_pressed: bool, debounced_pressed: bool) -> None:
        state_str = "PRESSED " if debounced_pressed else "RELEASED"
        current_layer = manager.current_layer
        bind = getattr(current_layer, name.lower(), None)
        action_desc = f"-> Key '{bind.key_char}'" if (bind and bind.enabled) else "-> (Unbound)"
        if bind and bind.is_macro:
            action_desc = f"-> Macro: '{bind.macro_text}'"

        print(f"  [PADDLE] {name:<8} {state_str:<9} (Raw: {raw_pressed})  [Layer: {current_layer.name}] {action_desc}", flush=True)

    def on_layer_switch(layer_num: int, layer_name: str) -> None:
        print(f"\n>>> [LAYER SWITCH] Active Layer: {layer_num} - {layer_name} <<<\n", flush=True)

    def on_status_change(dongle_status: DeviceStatus, dongle_desc: str, ctrl_status: DeviceStatus, ctrl_desc: str) -> None:
        print(f"  [STATUS] Dongle: {dongle_status.value} ({dongle_desc}) | Controller: {ctrl_status.value} ({ctrl_desc})", flush=True)

    manager.on_paddle_event = on_paddle
    manager.on_layer_changed = on_layer_switch
    manager.on_status_updated = on_status_change

    # Auto-switch watchdog (if enabled)
    auto_switcher = None
    if global_cfg.get("auto_switch", True):
        def on_auto_switch(new_p: Profile) -> None:
            print(f"\n>>> [AUTO-SWITCH] Target process foregrounded -> Switching to profile: {new_p.name} <<<\n")
            manager.set_profile(new_p)

        auto_switcher = config.AutoSwitchWatchdog(
            profiles_provider=lambda: all_profiles,
            active_profile_provider=lambda: manager.profile,
            switch_profile_callback=on_auto_switch,
        )
        auto_switcher.start()

    # Graceful shutdown handler
    def shutdown(signum=None, frame=None) -> NoReturn:
        print("\nStopping ShadowLink sniffer...")
        if auto_switcher:
            auto_switcher.stop()
        manager.stop()
        print("Shutdown complete. Bye!")
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start controller polling threads
    manager.start()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
