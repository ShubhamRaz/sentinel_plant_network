# ESP32-S3 firmware build and bench validation

The firmware uses the Protocol v2.0 hardware scope: ESP32-S3, SX1262, BME280, MLX90614, capacitive soil/leaf-wetness inputs, latching valve and YF-S201 flow meter.

## Build

Install PlatformIO Core and run from the repository root:

\`\`\`bash
pio run -c firmware/platformio.ini -e node_a
pio run -c firmware/platformio.ini -e node_b
pio run -c firmware/platformio.ini -e gateway
\`\`\`

The PlatformIO build wrappers in \`firmware/esp32_build/\` include the corresponding Arduino sketch. Node A is built with ID 1; Node B with ID 2. Dependencies are pinned in \`firmware/platformio.ini\`.

## Board/module configuration that must be completed

The Protocol v2.0 GPIO table specifies SX1262 CS, MOSI, SCK, MISO and DIO1, but does not allocate the module-specific RESET and BUSY pins. The default PlatformIO flags set both to \`-1\` (\`RADIOLIB_NC\`) only as a build placeholder. Confirm the exact SX1262 breakout schematic and assign valid pins before deployment. Some modules will not initialise without RESET/BUSY wiring.

The midday 11:30–14:30 rule requires local time. The current gateway has a compile-time \`SENTINEL_START_MINUTE_OF_DAY\` offset from boot; this is not a clock. Supply a trustworthy time source (or set the offset at each boot and document drift) before using time-window control. Daily disease severity is accumulated against a monotonic day boundary and therefore needs wall-clock/RTC integration for calendar-day epidemiological interpretation.

The software still requires validation of:
- Adafruit driver/API compatibility with the exact ESP32 Arduino core and sensor boards.
- Soil and leaf-wetness calibration constants in the target soil and mounting geometry.
- Radio link budget, antenna, legal EIRP, packet loss and node scheduling.
- YF-S201 pulses-per-litre calibration and hydraulic minimum-flow behaviour.
- Valve polarity, H-bridge electrical protection, flyback/inductive transients and physical shutoff.
- Continuous lockout timing, restart persistence, and safe manual reset procedures.

## Mandatory bench sequence

1. Keep the valve disconnected and replace it with a dummy indicator/load.
2. Verify I2C address detection and compare BME280/MLX90614 readings with references.
3. Verify raw ADC ranges, calibrate VWC and leaf-wetness sensors, and test disconnected-probe flags.
4. Verify SX1262 TX/RX, 24-byte packet size, CRC rejection, sequence numbers and stale packet handling.
5. Inject stale telemetry, missing sensor flags and corrupted packets; confirm valve output remains closed.
6. Calibrate flow pulses with a measured volume and verify zero-flow fault latching.
7. Verify H-bridge pulse width and open/close polarity with the valve disconnected.
8. Only then test the latching valve on an isolated water loop with a physical manual shutoff.

This code is a testable engineering baseline, not safety-certified production firmware. Because a latching valve retains its state after power loss, software shutdown alone is not a physical fail-safe.
