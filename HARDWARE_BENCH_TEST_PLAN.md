# Sentinel Plant Network — Hardware Bench Testing Plan & Verification Protocol

**Protocol Version:** Protocol v2.0  
**Target Hardware:** ESP32-S3-WROOM-1, SX1262 LoRa, BME280, MLX90614, Capacitive Probes, 12V Latching Valve, YF-S201 Flow Meter  
**Document Purpose:** Define exhaustive, bench-level physical verification procedures, signal pinouts, calibration requirements, failure simulations, and acceptance criteria prior to future agricultural field deployment.  
**Research Scope:** Future Physical Engineering Work (Out of Scope for Current Dataset/Simulation Manuscript).  

> [!IMPORTANT]
> **Scope Notice — Future Physical Work (Out of Scope for Current Manuscript):**  
> The current Sentinel Plant Network journal publication is a computational architecture, digital-twin benchmark, and external public-dataset validation study. Physical hardware fabrication, LoRa radio-frequency bench testing, latching-valve hydraulic loop verification, and in-situ sensor calibration are engineering procedures scheduled for future physical field deployment. No physical hardware deployment or field trials are claimed in the paper. This plan defines the pre-deployment verification criteria for future physical bench testing.

> [!WARNING]
> **Bench Safety Precaution:** Never perform initial valve testing with pressurized agricultural lines connected. Bench-test the H-bridge and latching solenoid valve using a low-pressure water loop or dry solenoid click verification. Latching valves mechanically retain their last state upon total power failure; ensure manual isolation valves are in place.

---

## 1. Physical Pin Allocation & Electrical Hardware Map

### 1.1 Field Sensing Nodes (Node A — Humid Pole; Node B — Dry Pole)
- **Microcontroller:** ESP32-S3-WROOM-1 (Dual-core Xtensa LX7, 240 MHz, 512 KB SRAM, 8 MB Flash).

| ESP32-S3 Pin | Signal Name | Electrical Interface | Connected Module / Transducer | Bench Verification Objective |
| :--- | :--- | :--- | :--- | :--- |
| **GPIO4** | `ADC_LWS` | Analog (ADC1_CH3) | Capacitive Leaf Wetness Probe | Measure 0--4095 ADC counts across dry vs. wet conditions |
| **GPIO5** | `ADC_SOIL` | Analog (ADC1_CH4) | Capacitive Soil Moisture Probe (15 & 30 cm) | Measure dry-air ADC vs. water-saturated soil ADC |
| **GPIO6** | `ADC_VBAT` | Analog (ADC1_CH5) | 2:1 Precision Resistor Divider (100k/100k) | Battery voltage telemetry ($V_{\text{bat}} = 2 \times V_{\text{ADC}}$) |
| **GPIO7** | `PWR_GATE` | Digital Output | High-Side P-MOSFET Gate (Active LOW) | Power gating dielectric probes; verify 0 mA quiescent in sleep |
| **GPIO8** | `I2C_SDA` | I2C (100 kHz) | Shared: Bosch BME280 & Melexis MLX90614 | Address scan (`0x76`/`0x77` BME280; `0x5A` MLX90614) |
| **GPIO9** | `I2C_SCL` | I2C (100 kHz) | Shared: Bosch BME280 & Melexis MLX90614 | Shared I2C bus pull-up verification (4.7 k$\Omega$ to 3.3V) |
| **GPIO10** | `LORA_CS` | SPI (4 MHz) | Semtech SX1262 SPI Chip Select | SPI bus chip enable |
| **GPIO11** | `LORA_MOSI` | SPI (4 MHz) | Semtech SX1262 MOSI | Master Out Slave In |
| **GPIO12** | `LORA_SCK` | SPI (4 MHz) | Semtech SX1262 SCK | SPI Clock |
| **GPIO13** | `LORA_MISO` | SPI (4 MHz) | Semtech SX1262 MISO | Master In Slave Out |
| **GPIO14** | `LORA_DIO1` | Digital Input | Semtech SX1262 DIO1 (Tx/Rx Done Interrupt) | LoRa packet transmission complete interrupt |
| **GPIO21** | `LORA_BUSY`* | Digital Input | Semtech SX1262 BUSY Status | **Mandatory hardware confirmation** (replace `RADIOLIB_NC`) |
| **GPIO47** | `LORA_RST`* | Digital Output | Semtech SX1262 Active-Low Reset | **Mandatory hardware confirmation** (replace `RADIOLIB_NC`) |

*\*Note: In `firmware/platformio.ini`, `SENTINEL_LORA_RST_PIN` and `SENTINEL_LORA_BUSY_PIN` default to `-1` (`RADIOLIB_NC`). On physical custom PCBs or breakout modules (e.g., Waveshare SX1262, Heltec), `BUSY` and `RST` must be physically connected to free GPIOs (e.g. GPIO21 and GPIO47) to avoid SPI lockups during internal LDO/DC-DC startup.*

### 1.2 Local Edge Gateway & Actuation Manifold

| ESP32-S3 Pin | Signal Name | Electrical Interface | Connected Module / Actuator | Bench Verification Objective |
| :--- | :--- | :--- | :--- | :--- |
| **GPIO10--14** | `LORA_SPI` | SPI Bus | Semtech SX1262 LoRa Receiver | Receive 24-byte telemetry packets from Node A and Node B |
| **GPIO15** | `VALVE_OPEN` | Digital Output | H-Bridge (e.g., DRV8871 / L298N) IN1 | Deliver 80 ms forward 12V pulse to unseat latching plunger |
| **GPIO16** | `VALVE_CLOSE`| Digital Output | H-Bridge (e.g., DRV8871 / L298N) IN2 | Deliver 80 ms reverse 12V pulse to seat latching plunger |
| **GPIO17** | `FLOW_PULSE` | Digital Input (Pullup) | YF-S201 Hall-Effect Flow Sensor | Interrupt-driven pulse accumulator (`onFlowPulse()`) |
| **GPIO8/9** | `I2C_RTC`* | I2C Bus | External DS3231 Real-Time Clock Module | **Recommended hardware addition** for true diurnal clock |

---

## 2. Unresolved Hardware Details & Pre-Bench Actions

Prior to applying power on the bench, the engineering team must resolve the following five items:

1. **SX1262 BUSY and RESET Pin Assignment:**
   - In RadioLib, calling `SX1262 radio = new Module(CS, DIO1, RST, BUSY)` with `RADIOLIB_NC` relies on soft-reset and timed delays. On many commercial modules, SPI transactions hang waiting for BUSY to go low.
   - *Action:* Trace PCB tracks from the SX1262 module. Allocate specific ESP32-S3 pins (e.g. GPIO21 for BUSY, GPIO47 for RST) and update `firmware/platformio.ini`.
2. **H-Bridge Valve Pulse Polarity:**
   - Latching valves use permanent magnets: a positive 12V pulse opens the valve, while a reverse pulse closes it. If IN1/IN2 connections are inverted, the firmware will open the valve when intending to close it.
   - *Action:* Verify polarity using a bench multimeter and oscilloscope. Confirm that pulsing `PIN_VALVE_OPEN` creates a positive pulse on the solenoid red lead, producing an audible plunger click.
3. **YF-S201 Flow Meter Calibration (K-Factor):**
   - The catalog value $450\text{ pulses/L}$ (approx. $7.5\text{ Hz}$ per L/min) varies by $\pm 10\%$ depending on inlet pressure and pipe diameter.
   - *Action:* Perform a 10-liter bucket volumetric test across flow rates from 2.0 to 12.0 L/min to compute the exact physical K-factor.
4. **Dielectric Probe Soil & Wetness Calibration:**
   - The default constants in `node_firmware.ino` (`SOIL_ADC_DRY = 3150`, `SOIL_ADC_SAT = 1280`, `LWS_DIELECTRIC_THRESH = 1850`) are uncalibrated placeholders.
   - *Action:* Perform two-point calibration using air/oven-dried target soil for the dry limit and saturated soil slurry for the wet limit. For leaf wetness, determine the threshold using dry sensor air counts versus deionized water droplet mist.
5. **Gateway Timekeeping Source:**
   - The firmware currently computes minute-of-day as monotonic `millis()` from an arbitrary startup offset `#define SENTINEL_START_MINUTE_OF_DAY 0`.
   - *Action:* Connect an external DS3231 I2C RTC module to GPIO8/GPIO9 or an ESP32 SNTP WiFi/cellular link so that the 11:30--14:30 solar window is locked to true solar time.

---

## 3. Step-by-Step Hardware Bench Testing Sequence

### Test 1: Power Subsystem & Quiescent Deep-Sleep Current
- **Apparatus:** Precision digital multimeter / current profile analyzer (e.g., Nordic Power Profiler Kit II or Keithley DMM6500), 3.2V LiFePO4 battery cell, 6V 3W solar panel, variable DC power supply.
- **Procedure:**
  1. Connect power analyzer in series with the 3.2V battery input.
  2. Boot the node and monitor the active sensor acquisition and LoRa transmit burst current ($I_{\text{peak}}$).
  3. Verify that `GPIO7` asserts `HIGH` to turn off the P-MOSFET power gate.
  4. Measure steady-state quiescent current during deep sleep.
- **Pass Criteria:**
  - Peak radio transmit current ($+22\text{ dBm}$): $\le 125\text{ mA}$.
  - Active sensor acquisition window: $\le 250\text{ ms}$ at $\le 35\text{ mA}$.
  - Deep-sleep quiescent current: $\le 25\text{ }\mu\text{A}$.
  - Calculated autonomy without solar input: $\ge 200\text{ hours}$ (matches Eq.~1: 9.8 days).

### Test 2: Shared I2C Sensor Acquisition & Error Handling
- **Apparatus:** Oscilloscope, logic analyzer on GPIO8 (SDA) and GPIO9 (SCL), BME280, MLX90614.
- **Procedure:**
  1. Execute I2C bus scan at 100 kHz. Confirm responses at `0x76` (or `0x77`) and `0x5A`.
  2. Verify that I2C bus timeout (`Wire.setTimeOut(50)`) prevents infinite blocking if a sensor disconnects.
  3. Disconnect MLX90614 during runtime: verify that firmware returns `NAN`, sets status flag `MLX_OK = 0`, and continues execution without watchdog reset.
- **Pass Criteria:**
  - Clean I2C clock and data transitions with rise times $< 1\text{ }\mu\text{s}$ (4.7 k$\Omega$ pullups).
  - Plausible ambient readings: $T_a \in [15, 35]^\circ\text{C}$, $\mathrm{RH} \in [20, 95]\%$.
  - Disconnection returns `NAN` and does not hang the MCU.

### Test 3: Dielectric Sensor Power Gating & ADC Linearity
- **Apparatus:** Oscilloscope on GPIO7 (Gate) and sensor $V_{\mathrm{CC}}$, calibrated reference soil container.
- **Procedure:**
  1. Trigger wakeup cycle. Measure delay between `GPIO7 = LOW` and ADC sampling.
  2. Confirm stabilization window of exactly $150\text{ ms}$.
  3. Measure sensor $V_{\mathrm{CC}}$: must drop to $< 0.1\text{ V}$ when `GPIO7 = HIGH`.
  4. Collect 16-sample averaged ADC reading (`readAveragedAdc()`) across dry air and moist soil.
- **Pass Criteria:**
  - Inactive sensor rail voltage: $< 50\text{ mV}$.
  - ADC standard deviation over 16 consecutive oversampled bursts: $\sigma < 5\text{ counts}$.

### Test 4: SX1262 LoRa Telemetry Link & CRC-16 Bit Validation
- **Apparatus:** Field Node A running `node_firmware.ino`, Edge Gateway running `gateway_firmware.ino`, RF attenuator (30 dB), SDR / spectrum analyzer.
- **Procedure:**
  1. Program Node A with `SENTINEL_NODE_ID=1`.
  2. Program Node B with `SENTINEL_NODE_ID=2`.
  3. Monitor LoRa link in 865--867 MHz India ISM band (+22 dBm, SF9, BW 125 kHz, CR 4/5).
  4. Gateway logs raw received payload bytes: verify exact length of 24 bytes and magic byte `0xA5`.
  5. Manually inject bit-flips in byte 10: verify that `sentinel::validatePacket()` rejects invalid CRC.
- **Pass Criteria:**
  - Packet reception rate $> 99\%$ across bench distance with 30 dB attenuation.
  - Zero packet parsing buffer overruns; invalid CRC packets immediately discarded.
  - Telemetry packet size strictly conforms to `static_assert(sizeof(SentinelPacket) == 24)`.

### Test 5: Six-State Gateway FSM Controller Verification
- **Apparatus:** Gateway connected to serial terminal; simulated packet injector sending synthetic test packets to evaluate state transitions.
- **Procedure:**
  1. **State 0 (`HOMEOSTASIS`):** Send normal telemetry ($T_{a}=22^\circ\text{C}, \mathrm{RH}=60\%, \theta=28\%, \mathrm{CWSI}=0.20, \mathrm{DSV}=0$). Output: Valve closed.
  2. **State 1 (`STANDARD_DRIP`):** Inject dry soil $\theta_B = 21.0\%$ ($\le 22\%$ MAD), $\mathrm{DSV}=0$. Output: Valve opened.
  3. **State 2 (`PATHOGEN_LOCKOUT`):** Inject accumulated $\mathrm{DSV} = 19$ ($\ge 18$) while $\theta_B = 26.0\%$ (non-stressed). Output: Valve closed.
  4. **State 3 (`CONFLICT_MICRO_PULSE`):** Inject drought stress ($\theta_B = 20.0\%$) AND pathogen risk ($\mathrm{DSV} = 19$). Set clock to 12:00 (720 min, inside 11:30--14:30). Output: 15 min ON / 45 min OFF pulsing.
  5. **State 4 (`EMERGENCY_DRIP`):** Inject severe drought $\theta_B = 15.5\%$ ($\le 16.0\%$ emergency floor) during active pathogen lockout. Output: Overrides lockout to open valve.
  6. **State 5 (`FAULT_FALLBACK`):** Cease telemetry from Node A for $> 30\text{ minutes}$ (1,800 s). Output: Valve closed, fault alert emitted.
- **Pass Criteria:**
  - 100% agreement with `sentinel::evaluateController()` specification in `sentinel_protocol.h`.

### Test 6: Latching Valve H-Bridge Pulse & Hydraulic Verifications
- **Apparatus:** 12V 2A DC supply, DRV8871 H-bridge, 12V latching solenoid valve, pressure gauge, water test bench (1--3 bar).
- **Procedure:**
  1. Connect oscilloscope across solenoid coils. Command valve open.
  2. Measure pulse duration: must be exactly $80\text{ ms} \pm 5\text{ ms}$.
  3. Verify that valve latches open and current drops to 0 mA after 80 ms.
  4. Command valve close. Verify reverse $80\text{ ms}$ pulse.
  5. Cut power supply to ESP32 while valve is latched open. Confirm that water continues flowing (confirming necessity of inline emergency shutoff).
- **Pass Criteria:**
  - Pulse width: $80\text{ ms} \pm 5\text{ ms}$.
  - Zero quiescent current drawn by solenoid outside the 80 ms actuation window.
  - Reliable mechanical latching across 50 consecutive open/close cycles under 2.0 bar water pressure.

### Test 7: Flow Meter Pulse Verification & Zero-Flow Fault Trip
- **Apparatus:** YF-S201 flow meter, inline with latching valve, pulse counter, calibrated catch container.
- **Procedure:**
  1. Command valve open. Run water through manifold at 5.0 L/min.
  2. Confirm interrupt triggers `flowPulseCount` in gateway firmware.
  3. Simulate supply failure: mechanically pinch inlet hose while valve is commanded open.
  4. Observe gateway response: after grace window ($60\text{ s}$), flow fault must latch (`flowFaultLatched = true`).
  5. Verify that controller immediately commands valve close and transitions to `FAULT_FALLBACK`.
- **Pass Criteria:**
  - Flow rate correctly computed within $\pm 5\%$ of volumetric catch.
  - Zero-flow condition while valve open trips `FAULT_FALLBACK` within 60 seconds.

---

## 4. Hardware Acceptance Criteria Matrix

| Subsystem / Test Item | Expected Input Condition | Required Physical Output / Metric | Acceptable Tolerance | Pass / Fail |
| :--- | :--- | :--- | :--- | :--- |
| **Deep Sleep Current** | Solar = 0V, MCU sleeping | Quiescent current from 3.2V rail | $\le 25.0\text{ }\mu\text{A}$ | Pending Bench |
| **Battery Autonomy** | $C_{\text{bat}} = 6000\text{ mAh}$, zero light | Total continuous run time | $\ge 200.0\text{ hours}$ | Pending Bench |
| **I2C Bus Robustness** | Unplug BME280 during read | Function returns `NAN`; no MCU reset | Timeout $\le 50\text{ ms}$ | Pending Bench |
| **ADC Noise Floor** | Grounded ADC pin | Mean ADC count | $\le 10\text{ counts}$ | Pending Bench |
| **LoRa Packet CRC** | Corrupt 1 bit in 24-byte packet | Gateway rejects packet | 100% rejection | Pending Bench |
| **LoRa Link Range** | Nodes separated by 500m canopy | Packet Reception Rate (PRR) | $\ge 95.0\%$ | Pending Bench |
| **Latching Valve Pulse** | Command OPEN / CLOSE | Pulse width on H-bridge output | $80\text{ ms} \pm 5\text{ ms}$ | Pending Bench |
| **Valve Standby Power** | Valve in latched position | Current draw on 12V coil rail | $0.0\text{ mA}$ | Pending Bench |
| **Flow Meter Fault** | Valve open, 0 pulses for 60s | Controller transitions to State 5 | $\le 65\text{ s}$ | Pending Bench |
| **Packet Stale Timeout** | No telemetry for 30 minutes | Controller transitions to State 5 | $1800\text{ s} \pm 30\text{ s}$ | Pending Bench |
| **Emergency Drought Floor** | $\theta_B \le 16.0\%$ during blight lock | Emergency drip override activated | State 4 asserted immediately | Pending Bench |

---

## 5. Pre-Deployment Sign-Off Checklist

Before any hardware leaves the laboratory for agricultural field installation, the lead test engineer must verify and sign:

- [ ] SX1262 BUSY and RESET GPIO pins physically confirmed on PCB and compiled in `platformio.ini`.
- [ ] Two-point soil calibration curves ($V_{\text{ADC}} \to \%\text{ VWC}$) completed for target experimental station soil.
- [ ] Leaf wetness dielectric threshold validated with misting chamber.
- [ ] MLX90614 infrared optical window verified clean and field of view ($10^\circ$) aligned to lower-third canopy.
- [ ] H-bridge pulse polarity verified: OPEN command delivers positive pulse, CLOSE delivers negative pulse.
- [ ] YF-S201 pulses-per-liter calibrated with volumetric catch container.
- [ ] Gateway real-time clock (RTC) synchronized and verified across power-cycle resets.
- [ ] Enclosures sealed to IP66 standards with waterproof cable glands and Gore-Tex pressure equalization vents.
- [ ] LiFePO4 battery protection circuit module (PCM) confirmed to disconnect at $2.5\text{ V}$ cutoff.
- [ ] Manual override ball valve plumbed in parallel with latching solenoid valve for agronomic safety.
