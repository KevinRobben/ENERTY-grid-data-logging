
# Persistent USB CDC Serial Setup for ESP32-S2 on Raspberry Pi

This guide explains how to configure a Raspberry Pi to recognize your ESP32-S2 device with a custom USB VID/PID (`0403:80da`) as a USB CDC ACM serial device (`/dev/ttyACM0`) persistently.

---

## Background

Your ESP32-S2 uses a custom USB VID and PID, which Linux does not automatically bind to the `cdc_acm` driver. Without this binding, the device will not create the expected serial port (e.g., `/dev/ttyACM0`).

This guide shows how to add a udev rule to automatically bind your device to the `cdc_acm` driver whenever it is connected.

---

## Step 1: Verify Device Presence

Check that the device is connected and recognized on USB:

```bash
lsusb | grep 0403:80da
```

You should see output similar to:

```
Bus 001 Device 003: ID 0403:80da Your ESP32-S2 Device
```

---

## Step 2: Bind Device to `cdc_acm` Driver Temporarily (Test)

To confirm the binding works, run:

```bash
echo 0403 80da | sudo tee /sys/bus/usb/drivers/cdc_acm/new_id
```

Check the serial device node appears:

```bash
ls /dev/ttyACM*
```

You should see:

```
/dev/ttyACM0
```

---

## Step 3: Create a Persistent udev Rule

Create a new udev rules file:

```bash
sudo nano /etc/udev/rules.d/99-esp32-cdc.rules
```

Add the following content:

```udev
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="80da", RUN+="/bin/sh -c 'echo 0403 80da > /sys/bus/usb/drivers/cdc_acm/new_id'"
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

---

## Step 4: Reload udev Rules

Apply the new rule immediately:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

---

## Step 5: Confirm Persistent Binding

Check that `/dev/ttyACM0` exists (the device should already be connected):

```bash
ls /dev/ttyACM*
```

If `/dev/ttyACM0` is listed, your device is successfully bound to the `cdc_acm` driver persistently.

---

## Notes

- This setup ensures your ESP32-S2’s custom USB VID/PID is always handled correctly.
- Use `/dev/ttyACM0` in your serial communication scripts and applications.

---

## Troubleshooting

- If `/dev/ttyACM0` does not appear, verify the device is powered and connected.
- Check for typos in the udev rule file.
- Verify permissions: `sudo chmod 644 /etc/udev/rules.d/99-esp32-cdc.rules`.
- Check `dmesg` for USB and driver-related messages:

  ```bash
  dmesg | tail -30
  ```

---

## Summary

By adding the udev rule above, your Raspberry Pi will automatically bind your ESP32-S2 device’s USB interface to the native CDC ACM serial driver, providing `/dev/ttyACM0` for serial communication on every boot and connection.

---

Feel free to reach out if you need help automating this or integrating it with your update workflow!
