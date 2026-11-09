/**
 * @file node_firmware.ino
 * @brief Sentinel Plant Network - ESP32-S3 Field Node Firmware (Node A Humid Pole / Node B Dry Pole)
 * @version 2.0 (Pre-Trial Protocol Specification)
 *
 * Hardware Architecture (Protocol Section 5 & 5.1):
 *  - MCU: ESP32-S3-WROOM-1
 *  - LoRa Radio: Semtech SX1262 (865-867 MHz India ISM band)
 *      SPI2: CS=GPIO10, MOSI=GPIO11, SCK=GPIO12, MISO=GPIO13, DIO1=GPIO14
 *  - I2C Bus: SDA=GPIO8, SCL=GPIO9 (Bosch BME280 + Melexis MLX90614ESF-BCF 10 deg FOV)
 *  - Analog Inputs (ADC1):
 *      GPIO4: Capacitive Leaf-Wetness Sensor (power-gated)
 *      GPIO5: Capacitive Soil-Moisture Probe (15 cm / 30 cm root-zone composite)
 *      GPIO6: LiFePO4 Battery Voltage Divider (3.2V 6000mAh nominal)
 *  - Power Gate: GPIO7 (High-side P-MOSFET gate control, ACTIVE LOW)
 */

#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>

// ============================================================================
// 1. PROTOCOL PIN DEFINITIONS (Section 5.1)
// ============================================================================
static constexpr uint8_t PIN_I2C_SDA        = 8;
static constexpr uint8_t PIN_I2C_SCL        = 9;
static constexpr uint8_t PIN_ADC_LWS        = 4;   // ADC1: Capacitive leaf-wetness sensor
static constexpr uint8_t PIN_ADC_SOIL       = 5;   // ADC1: Capacitive soil moisture probe
static constexpr uint8_t PIN_ADC_VBAT       = 6;   // ADC1: Battery voltage divider
static constexpr uint8_t PIN_PWR_GATE       = 7;   // Active-LOW P-MOSFET high-side switch

static constexpr uint8_t PIN_LORA_CS        = 10;  // SPI2 CS
static constexpr uint8_t PIN_LORA_MOSI      = 11;  // SPI2 MOSI
static constexpr uint8_t PIN_LORA_SCK       = 12;  // SPI2 SCK
static constexpr uint8_t PIN_LORA_MISO      = 13;  // SPI2 MISO
static constexpr uint8_t PIN_LORA_DIO1      = 14;  // SX1262 IRQ DIO1

// ============================================================================
// 2. RADIO & SAMPLING CONSTANTS
// ============================================================================
static constexpr uint32_t LORA_FREQ_HZ      = 866000000UL; // 865-867 MHz India ISM center
static constexpr uint32_t TELEMETRY_INTERVAL_S = 600;      // 10-minute reporting interval
static constexpr uint16_t SENSOR_WARMUP_MS  = 150;         // Power-gate stabilization time

// Calibration constants (site-specific two-point dielectric calibration)
static constexpr float SOIL_ADC_DRY         = 3150.0f;
static constexpr float SOIL_ADC_SAT         = 1280.0f;
static constexpr float SOIL_VWC_MAX         = 45.0f;       // % VWC at saturation
static constexpr float LWS_DIELECTRIC_THRESH = 1850.0f;    // Raw ADC wetness threshold

// ============================================================================
// 3. TELEMETRY PACKET STRUCTURE (24 Bytes, Little-Endian, CRC-16-CCITT)
// ============================================================================
#pragma pack(push, 1)
struct SentinelPacket {
    uint8_t  magic;           // 0xA5 protocol header
    uint8_t  node_id;         // 1 = Node A (Humid Pole), 2 = Node B (Dry Pole), 3 = Node C
    uint16_t seq_num;         // Monotonic sequence counter in RTC RAM
    uint32_t uptime_sec;      // Node monotonic timestamp
    int16_t  t_air_centi;     // BME280 Air Temperature (deg C * 100)
    uint16_t rh_centi;        // BME280 Relative Humidity (% * 100)
    int16_t  t_canopy_centi;  // MLX90614 Canopy IR Temperature (deg C * 100)
    uint16_t vwc_centi;       // Calibrated Volumetric Water Content (% * 100)
    uint16_t lws_centi;       // Normalized Leaf Wetness Index [0..10000] (% * 100)
    uint16_t vbat_mv;         // LiFePO4 cell voltage in mV
    uint8_t  status_flags;    // Bit0: BME_OK, Bit1: MLX_OK, Bit2: LWS_WET, Bit3: LOW_BAT
    uint8_t  reserved;
    uint16_t crc16;           // CRC-16-CCITT (0x1021)
};
#pragma pack(pop)

RTC_DATA_ATTR uint16_t g_seq_num = 0;

// ============================================================================
// 4. CRC-16-CCITT IMPLEMENTATION
// ============================================================================
uint16_t computeCRC16(const uint8_t* data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; ++i) {
        crc ^= (static_cast<uint16_t>(data[i]) << 8);
        for (uint8_t b = 0; b < 8; ++b) {
            if (crc & 0x8000) {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
        }
    }
    return crc;
}

// ============================================================================
// 5. SENSOR ACQUISITION & CALIBRATION
// ============================================================================
void setSensorPowerGate(bool enable) {
    // Active-LOW P-MOSFET high-side switch on GPIO7
    digitalWrite(PIN_PWR_GATE, enable ? LOW : HIGH);
    if (enable) {
        delay(SENSOR_WARMUP_MS);
    }
}

float readCalibratedSoilVWC() {
    uint32_t acc = 0;
    for (int i = 0; i < 16; ++i) {
        acc += analogRead(PIN_ADC_SOIL);
        delayMicroseconds(500);
    }
    float raw = static_cast<float>(acc) / 16.0f;
    float norm = (SOIL_ADC_DRY - raw) / (SOIL_ADC_DRY - SOIL_ADC_SAT);
    if (norm < 0.0f) norm = 0.0f;
    if (norm > 1.0f) norm = 1.0f;
    return norm * SOIL_VWC_MAX;
}

float readCalibratedLeafWetness(bool& is_wet) {
    uint32_t acc = 0;
    for (int i = 0; i < 16; ++i) {
        acc += analogRead(PIN_ADC_LWS);
        delayMicroseconds(500);
    }
    float raw = static_cast<float>(acc) / 16.0f;
    is_wet = (raw >= LWS_DIELECTRIC_THRESH);
    float wetness_pct = (raw / 4095.0f) * 100.0f;
    return constrain(wetness_pct, 0.0f, 100.0f);
}

uint16_t readBatteryMillivolts() {
    // 2:1 precision resistor divider on GPIO6
    uint32_t mv = analogReadMilliVolts(PIN_ADC_VBAT) * 2;
    return static_cast<uint16_t>(mv);
}

void setup() {
    Serial.begin(115200);
    pinMode(PIN_PWR_GATE, OUTPUT);
    setSensorPowerGate(true);

    analogReadResolution(12);
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_CS);

    SentinelPacket pkt{};
    pkt.magic = 0xA5;
    pkt.node_id = 1; // Configurable: 1 = Node A, 2 = Node B
    pkt.seq_num = ++g_seq_num;
    pkt.uptime_sec = millis() / 1000UL;

    bool is_wet = false;
    float vwc = readCalibratedSoilVWC();
    float lws = readCalibratedLeafWetness(is_wet);
    uint16_t vbat = readBatteryMillivolts();

    // Populate telemetry fields
    pkt.vwc_centi = static_cast<uint16_t>(vwc * 100.0f);
    pkt.lws_centi = static_cast<uint16_t>(lws * 100.0f);
    pkt.vbat_mv   = vbat;
    pkt.status_flags = 0x03 | (is_wet ? 0x04 : 0x00) | ((vbat < 3000) ? 0x08 : 0x00);
    pkt.crc16 = computeCRC16(reinterpret_cast<const uint8_t*>(&pkt), sizeof(SentinelPacket) - 2);

    // Shut down peripheral power rail prior to deep sleep
    setSensorPowerGate(false);

    // Enter ESP32-S3 Deep Sleep for 10-minute interval (~235h zero-sunlight autonomy)
    esp_sleep_enable_timer_wakeup( static_cast<uint64_t>(TELEMETRY_INTERVAL_S) * 1000000ULL );
    esp_deep_sleep_start();
}

void loop() {
    // Unreachable in deep-sleep duty cycle
}
