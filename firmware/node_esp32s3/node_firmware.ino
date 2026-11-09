/**
 * Sentinel Plant Network - ESP32-S3 field node, Protocol v2.0.
 *
 * Dependencies: RadioLib, Adafruit BME280, Adafruit MLX90614, Adafruit Unified Sensor.
 * Build the same source twice: SENTINEL_NODE_ID=1 (humid pole A) and =2 (dry pole B).
 * The exact SX1262 module may require dedicated RESET/BUSY pins. The protocol pin
 * table does not allocate them; set SENTINEL_LORA_RST_PIN / SENTINEL_LORA_BUSY_PIN
 * to the correct board pins before hardware deployment. RADIOLIB_NC is only a
 * compile-time fallback and may not initialise every module.
 */
#include <Arduino.h>
#include <Wire.h>
#include <SPI.h>
#include <RadioLib.h>
#include <Adafruit_BME280.h>
#include <Adafruit_MLX90614.h>
#include "../common/sentinel_protocol.h"

#ifndef SENTINEL_NODE_ID
#define SENTINEL_NODE_ID 1
#endif
#ifndef SENTINEL_LORA_RST_PIN
#define SENTINEL_LORA_RST_PIN RADIOLIB_NC
#endif
#ifndef SENTINEL_LORA_BUSY_PIN
#define SENTINEL_LORA_BUSY_PIN RADIOLIB_NC
#endif

static constexpr uint8_t PIN_I2C_SDA = 8;
static constexpr uint8_t PIN_I2C_SCL = 9;
static constexpr uint8_t PIN_ADC_LWS = 4;
static constexpr uint8_t PIN_ADC_SOIL = 5;
static constexpr uint8_t PIN_ADC_VBAT = 6;
static constexpr uint8_t PIN_PWR_GATE = 7;
static constexpr uint8_t PIN_LORA_CS = 10;
static constexpr uint8_t PIN_LORA_MOSI = 11;
static constexpr uint8_t PIN_LORA_SCK = 12;
static constexpr uint8_t PIN_LORA_MISO = 13;
static constexpr uint8_t PIN_LORA_DIO1 = 14;

static constexpr uint32_t TELEMETRY_INTERVAL_S = 600;
static constexpr uint16_t SENSOR_WARMUP_MS = 150;
static constexpr float SOIL_ADC_DRY = 3150.0f;  // Replace with site calibration
static constexpr float SOIL_ADC_SAT = 1280.0f;  // Replace with site calibration
static constexpr float SOIL_VWC_MAX = 45.0f;
static constexpr float LWS_DIELECTRIC_THRESH = 1850.0f;  // Calibrate per probe
static constexpr uint16_t LOW_BATTERY_MV = 3000;

Adafruit_BME280 bme;
Adafruit_MLX90614 mlx;
SX1262 radio = new Module(PIN_LORA_CS, PIN_LORA_DIO1, SENTINEL_LORA_RST_PIN, SENTINEL_LORA_BUSY_PIN);
RTC_DATA_ATTR uint16_t sequenceNumber = 0;

void setSensorPowerGate(bool enabled) {
    digitalWrite(PIN_PWR_GATE, enabled ? LOW : HIGH);
    if (enabled) delay(SENSOR_WARMUP_MS);
}

float readAveragedAdc(uint8_t pin) {
    uint32_t total = 0;
    for (uint8_t i = 0; i < 16; ++i) {
        total += analogRead(pin);
        delayMicroseconds(500);
    }
    return static_cast<float>(total) / 16.0f;
}

float readSoilVwc() {
    const float raw = readAveragedAdc(PIN_ADC_SOIL);
    const float denominator = SOIL_ADC_DRY - SOIL_ADC_SAT;
    if (fabsf(denominator) < 1.0f) return NAN;
    float normalized = (SOIL_ADC_DRY - raw) / denominator;
    normalized = constrain(normalized, 0.0f, 1.0f);
    return normalized * SOIL_VWC_MAX;
}

float readLeafWetness(bool& wet) {
    const float raw = readAveragedAdc(PIN_ADC_LWS);
    wet = raw >= LWS_DIELECTRIC_THRESH;
    // Normalised ADC percentage; it is not a calibrated physical water film.
    return constrain((raw / 4095.0f) * 100.0f, 0.0f, 100.0f);
}

uint16_t readBatteryMillivolts() {
    // GPIO6 measures the midpoint of an externally protected 2:1 divider.
    return static_cast<uint16_t>(analogReadMilliVolts(PIN_ADC_VBAT) * 2U);
}

void enterNextSleep() {
    esp_sleep_enable_timer_wakeup(static_cast<uint64_t>(TELEMETRY_INTERVAL_S) * 1000000ULL);
    esp_deep_sleep_start();
}

void setup() {
    Serial.begin(115200);
    pinMode(PIN_PWR_GATE, OUTPUT);
    setSensorPowerGate(true);
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_ADC_LWS, ADC_11db);
    analogSetPinAttenuation(PIN_ADC_SOIL, ADC_11db);
    analogSetPinAttenuation(PIN_ADC_VBAT, ADC_11db);
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL, 100000);
    Wire.setTimeOut(50);
    SPI.begin(PIN_LORA_SCK, PIN_LORA_MISO, PIN_LORA_MOSI, PIN_LORA_CS);

    const bool bmeFound = bme.begin(0x76, &Wire) || bme.begin(0x77, &Wire);
    const bool mlxFound = mlx.begin(0x5A, &Wire);
    const float tAir = bmeFound ? bme.readTemperature() : NAN;
    const float rh = bmeFound ? bme.readHumidity() : NAN;
    const float pressureHpa = bmeFound ? bme.readPressure() / 100.0f : NAN;
    const float tCanopy = mlxFound ? mlx.readObjectTempC() : NAN;
    const float mlxAmbient = mlxFound ? mlx.readAmbientTempC() : NAN;
    const float vwc = readSoilVwc();
    bool leafWet = false;
    const float lws = readLeafWetness(leafWet);
    const uint16_t batteryMv = readBatteryMillivolts();

    sentinel::SentinelPacket packet{};
    packet.magic = 0xA5;
    packet.node_id = SENTINEL_NODE_ID;
    packet.seq_num = ++sequenceNumber;
    packet.uptime_sec = millis() / 1000U;
    packet.t_air_centi = isfinite(tAir) ? static_cast<int16_t>(lroundf(tAir * 100.0f)) : 0;
    packet.rh_centi = isfinite(rh) ? static_cast<uint16_t>(constrain(lroundf(rh * 100.0f), 0L, 10000L)) : 0;
    packet.t_canopy_centi = isfinite(tCanopy) ? static_cast<int16_t>(lroundf(tCanopy * 100.0f)) : 0;
    packet.vwc_centi = isfinite(vwc) ? static_cast<uint16_t>(constrain(lroundf(vwc * 100.0f), 0L, 65535L)) : 0;
    packet.lws_centi = isfinite(lws) ? static_cast<uint16_t>(constrain(lroundf(lws * 100.0f), 0L, 10000L)) : 0;
    packet.vbat_mv = batteryMv;
    packet.status_flags = (bmeFound && isfinite(tAir) && isfinite(rh) ? 0x01 : 0x00)
                        | (mlxFound && isfinite(tCanopy) ? 0x02 : 0x00)
                        | (leafWet ? 0x04 : 0x00)
                        | (batteryMv < LOW_BATTERY_MV ? 0x08 : 0x00);
    packet.reserved = 0;
    packet.crc16 = sentinel::crc16Ccitt(
        reinterpret_cast<const uint8_t*>(&packet), sizeof(packet) - sizeof(packet.crc16)
    );

    Serial.printf("Node %u seq=%u VWC=%.2f LWS=%.1f Ta=%.2f RH=%.1f Tc=%.2f P=%.1f hPa MLX-Ta=%.2f battery=%u mV\n",
                  packet.node_id, packet.seq_num, vwc, lws, tAir, rh, tCanopy, pressureHpa, mlxAmbient, batteryMv);

    radio.setDio2AsRfSwitch(true);
    const int16_t radioState = radio.begin(866.0, 125.0, 9, 5, 0x12, 22, 8, 1.6, false);
    bool txOk = false;
    if (radioState == RADIOLIB_ERR_NONE) {
        for (uint8_t attempt = 0; attempt < 2 && !txOk; ++attempt) {
            const int16_t txState = radio.transmit(reinterpret_cast<uint8_t*>(&packet), sizeof(packet));
            txOk = txState == RADIOLIB_ERR_NONE;
            if (!txOk) delay(100);
        }
        radio.sleep();
    } else {
        Serial.printf("SX1262 init failed: %d\n", radioState);
    }
    Serial.printf("LoRa TX: %s\n", txOk ? "OK" : "FAILED");
    // Pressure is logged locally; the fixed 24-byte Protocol v2.0 packet has no pressure field.
    setSensorPowerGate(false);
    enterNextSleep();
}

void loop() {
    // One sensing/transmit cycle per deep-sleep wake.
}
