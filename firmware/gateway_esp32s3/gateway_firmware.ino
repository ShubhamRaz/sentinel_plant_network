/**
 * Sentinel Plant Network - ESP32-S3 local gateway, Protocol v2.0.
 *
 * Dependency: RadioLib. Configure SX1262 RESET/BUSY pins for the exact module.
 * A real wall-clock source is not in the current hardware specification: set
 * SENTINEL_START_MINUTE_OF_DAY at boot or integrate a validated RTC/NTP source.
 * This build uses a monotonic offset from the configured startup time.
 *
 * Bench-test with the valve disconnected. A latching valve retains its last
 * position after power loss; provide physical isolation/fail-safe plumbing.
 * Calibrate the YF-S201 pulses-per-litre and every sensor threshold before use.
 */
#include <Arduino.h>
#include <SPI.h>
#include <RadioLib.h>
#include <math.h>
#include <algorithm>
#include "../common/sentinel_protocol.h"

#ifndef SENTINEL_LORA_RST_PIN
#define SENTINEL_LORA_RST_PIN RADIOLIB_NC
#endif
#ifndef SENTINEL_LORA_BUSY_PIN
#define SENTINEL_LORA_BUSY_PIN RADIOLIB_NC
#endif
#ifndef SENTINEL_START_MINUTE_OF_DAY
#define SENTINEL_START_MINUTE_OF_DAY 0
#endif

static constexpr uint8_t PIN_LORA_CS = 10, PIN_LORA_MOSI = 11, PIN_LORA_SCK = 12;
static constexpr uint8_t PIN_LORA_MISO = 13, PIN_LORA_DIO1 = 14;
static constexpr uint8_t PIN_VALVE_OPEN = 15, PIN_VALVE_CLOSE = 16, PIN_FLOW_SENSOR = 17;
static constexpr uint32_t LATCH_PULSE_MS = 80;
static constexpr uint32_t FLOW_WINDOW_MS = 10000;
static constexpr uint32_t FLOW_FAULT_GRACE_MS = 60000;
static constexpr float FLOW_PULSES_PER_LITRE = 450.0f;  // Field-calibrate
static constexpr float MIN_FLOW_LPM = 0.2f;
static constexpr uint32_t PAIR_WINDOW_MS = 11UL * 60UL * 1000UL;
static constexpr size_t SUFFICIENCY_WINDOW = 288;

SX1262 radio = new Module(PIN_LORA_CS, PIN_LORA_DIO1, SENTINEL_LORA_RST_PIN, SENTINEL_LORA_BUSY_PIN);

struct NodeState {
    sentinel::SentinelPacket packet{};
    uint32_t last_rx_ms = 0;
    bool valid = false;
    bool updated = false;
};
NodeState nodeA, nodeB, nodeC;

volatile uint32_t flowPulseCount = 0;
portMUX_TYPE flowMux = portMUX_INITIALIZER_UNLOCKED;
void IRAM_ATTR onFlowPulse() {
    portENTER_CRITICAL_ISR(&flowMux);
    ++flowPulseCount;
    portEXIT_CRITICAL_ISR(&flowMux);
}
uint32_t readFlowPulses() {
    portENTER_CRITICAL(&flowMux);
    const uint32_t value = flowPulseCount;
    portEXIT_CRITICAL(&flowMux);
    return value;
}

bool valveIsOpen = false, valvePulseActive = false;
uint32_t valvePulseStopMs = 0, valveOpenedAtMs = 0;
uint32_t lastFlowWindowMs = 0, lastFlowSnapshot = 0;
float measuredFlowLpm = 0.0f;
bool flowFault = false, flowFaultLatched = false;

float lwsHoursToday = 0.0f, rh90HoursToday = 0.0f, temperatureSumRh90 = 0.0f;
uint32_t temperatureCountRh90 = 0;
uint16_t accumulatedWallinDsv = 0, accumulatedLwsDsv = 0;
uint32_t monotonicDay = 0;

float vwcAHistory[SUFFICIENCY_WINDOW]{}, vwcBHistory[SUFFICIENCY_WINDOW]{};
size_t pairHead = 0, pairCount = 0;
uint16_t consumedASeq = 0, consumedBSeq = 0;
bool hasConsumedPair = false, insufficientCoverage = true;
float latestVwcDivergence = NAN, latestSpearman = NAN;
uint32_t startupMs = 0, lastControllerLogMs = 0, lockoutStartedMs = 0;
bool lockoutTimerActive = false;
sentinel::ControllerState currentState = sentinel::ControllerState::FAULT_FALLBACK;
sentinel::ProtocolThresholds thresholds;

float packetValue(uint16_t value) { return static_cast<float>(value) / 100.0f; }
float packetTemp(int16_t value) { return static_cast<float>(value) / 100.0f; }

uint16_t wallinDsv(float meanTempC, float rh90Hours) {
    if (!isfinite(meanTempC) || !isfinite(rh90Hours) || meanTempC < 7.2f || meanTempC > 26.6f) return 0;
    if (meanTempC <= 11.6f) {
        if (rh90Hours < 16.0f) return 0;
        if (rh90Hours <= 18.0f) return 1;
        if (rh90Hours <= 21.0f) return 2;
        if (rh90Hours <= 23.0f) return 3;
        return 4;
    }
    if (meanTempC <= 15.0f) {
        if (rh90Hours < 13.0f) return 0;
        if (rh90Hours <= 15.0f) return 1;
        if (rh90Hours <= 18.0f) return 2;
        if (rh90Hours <= 21.0f) return 3;
        return 4;
    }
    if (rh90Hours < 10.0f) return 0;
    if (rh90Hours <= 12.0f) return 1;
    if (rh90Hours <= 15.0f) return 2;
    if (rh90Hours <= 18.0f) return 3;
    return 4;
}

void accumulateNodeADailyWeather(const sentinel::SentinelPacket& packet) {
    const uint32_t dayNow = millis() / 86400000UL;  // Monotonic day, not calendar time.
    if (dayNow != monotonicDay) {
        const float meanWetTemp = temperatureCountRh90
            ? temperatureSumRh90 / static_cast<float>(temperatureCountRh90) : NAN;
        const uint16_t base = wallinDsv(meanWetTemp, rh90HoursToday);
        const float effectiveWetHours = fmaxf(rh90HoursToday, 0.85f * lwsHoursToday + 0.15f * rh90HoursToday);
        const uint16_t modified = wallinDsv(meanWetTemp, effectiveWetHours);
        accumulatedWallinDsv = static_cast<uint16_t>(accumulatedWallinDsv + base);
        accumulatedLwsDsv = static_cast<uint16_t>(accumulatedLwsDsv + modified);
        monotonicDay = dayNow;
        lwsHoursToday = rh90HoursToday = temperatureSumRh90 = 0.0f;
        temperatureCountRh90 = 0;
    }
    const float rh = packetValue(packet.rh_centi);
    const float lws = packetValue(packet.lws_centi);
    const float temp = packetTemp(packet.t_air_centi);
    if (rh >= 90.0f) {
        rh90HoursToday += 10.0f / 60.0f;
        if (isfinite(temp)) { temperatureSumRh90 += temp; ++temperatureCountRh90; }
    }
    if (lws >= 50.0f) lwsHoursToday += 10.0f / 60.0f;
}

void updateNode(NodeState& state, const sentinel::SentinelPacket& packet) {
    state.packet = packet;
    state.last_rx_ms = millis();
    state.updated = true;
    const bool bmeOk = (packet.status_flags & 0x01U) != 0;
    const bool mlxOk = (packet.status_flags & 0x02U) != 0;
    const bool soilOk = (packet.status_flags & 0x10U) != 0;
    const bool leafWetnessOk = (packet.status_flags & 0x20U) != 0;
    const float vwc = packetValue(packet.vwc_centi);
    state.valid = bmeOk && mlxOk && soilOk && leafWetnessOk && isfinite(vwc) && vwc <= 65.0f;
    if (&state == &nodeA) accumulateNodeADailyWeather(packet);
}

void receiveLoRaPacket() {
    const uint16_t irq = radio.getIrqFlags();
    if ((irq & RADIOLIB_SX126X_IRQ_RX_DONE) == 0) return;
    uint8_t buffer[64]{};
    const size_t packetLength = radio.getPacketLength();
    const int16_t readState = radio.readData(buffer, sizeof(buffer));
    radio.startReceive();
    if (readState != RADIOLIB_ERR_NONE || packetLength != sizeof(sentinel::SentinelPacket)) {
        Serial.printf("Rejected LoRa payload: state=%d length=%u\n", readState, static_cast<unsigned>(packetLength));
        return;
    }
    sentinel::SentinelPacket packet{};
    if (!sentinel::validatePacket(buffer, packetLength, packet)) {
        Serial.println("Rejected LoRa payload: magic/length/CRC/node ID invalid");
        return;
    }
    if (packet.node_id == 1) updateNode(nodeA, packet);
    else if (packet.node_id == 2) updateNode(nodeB, packet);
    else updateNode(nodeC, packet);
}

float spearmanFromHistory(size_t n) {
    if (n < 3) return NAN;
    float rankA[SUFFICIENCY_WINDOW], rankB[SUFFICIENCY_WINDOW];
    float a[SUFFICIENCY_WINDOW], b[SUFFICIENCY_WINDOW];
    for (size_t i = 0; i < n; ++i) {
        const size_t p = (pairHead + SUFFICIENCY_WINDOW - n + i) % SUFFICIENCY_WINDOW;
        a[i] = vwcAHistory[p]; b[i] = vwcBHistory[p];
    }
    for (size_t i = 0; i < n; ++i) {
        float lessA=0, equalA=0, lessB=0, equalB=0;
        for (size_t j = 0; j < n; ++j) {
            if (a[j] < a[i]) lessA += 1.0f;
            if (a[j] == a[i]) equalA += 1.0f;
            if (b[j] < b[i]) lessB += 1.0f;
            if (b[j] == b[i]) equalB += 1.0f;
        }
        rankA[i] = lessA + (equalA + 1.0f) / 2.0f;
        rankB[i] = lessB + (equalB + 1.0f) / 2.0f;
    }
    float meanA=0, meanB=0;
    for (size_t i=0; i<n; ++i) { meanA += rankA[i]; meanB += rankB[i]; }
    meanA /= n; meanB /= n;
    float covariance=0, varA=0, varB=0;
    for (size_t i=0; i<n; ++i) {
        const float da=rankA[i]-meanA, db=rankB[i]-meanB;
        covariance += da*db; varA += da*da; varB += db*db;
    }
    const float denominator=sqrtf(varA*varB);
    return denominator>0 ? covariance/denominator : 0.0f;
}

void updateSpatialSufficiency() {
    if (!nodeA.updated || !nodeB.updated) return;
    if (hasConsumedPair && (nodeA.packet.seq_num == consumedASeq || nodeB.packet.seq_num == consumedBSeq)) return;
    if (!nodeA.valid || !nodeB.valid) return;
    const uint32_t delta = nodeA.last_rx_ms > nodeB.last_rx_ms
        ? nodeA.last_rx_ms-nodeB.last_rx_ms : nodeB.last_rx_ms-nodeA.last_rx_ms;
    if (delta > PAIR_WINDOW_MS) return;
    consumedASeq=nodeA.packet.seq_num; consumedBSeq=nodeB.packet.seq_num; hasConsumedPair=true;
    vwcAHistory[pairHead]=packetValue(nodeA.packet.vwc_centi);
    vwcBHistory[pairHead]=packetValue(nodeB.packet.vwc_centi);
    pairHead=(pairHead+1)%SUFFICIENCY_WINDOW;
    if (pairCount<SUFFICIENCY_WINDOW) ++pairCount;
    if (pairCount<SUFFICIENCY_WINDOW) return;
    float sumDiff=0;
    for(size_t i=0;i<pairCount;++i){
        const size_t p=(pairHead+SUFFICIENCY_WINDOW-pairCount+i)%SUFFICIENCY_WINDOW;
        sumDiff += fabsf(vwcAHistory[p]-vwcBHistory[p]);
    }
    latestVwcDivergence=sumDiff/static_cast<float>(pairCount);
    latestSpearman=spearmanFromHistory(pairCount);
    insufficientCoverage=latestVwcDivergence>10.0f || latestSpearman<0.70f;
}

void startValveLatchPulse(bool open) {
    digitalWrite(PIN_VALVE_OPEN, LOW);
    digitalWrite(PIN_VALVE_CLOSE, LOW);
    digitalWrite(open ? PIN_VALVE_OPEN : PIN_VALVE_CLOSE, HIGH);
    valvePulseActive=true;
    valvePulseStopMs=millis()+LATCH_PULSE_MS;
    valveIsOpen=open;
    if(open) valveOpenedAtMs=millis();
}
void serviceValveLatchPulse() {
    if(valvePulseActive && static_cast<int32_t>(millis()-valvePulseStopMs)>=0){
        digitalWrite(PIN_VALVE_OPEN,LOW); digitalWrite(PIN_VALVE_CLOSE,LOW); valvePulseActive=false;
    }
}
void commandValve(bool open) {
    if(open!=valveIsOpen && !valvePulseActive) startValveLatchPulse(open);
}

void updateFlowFault() {
    const uint32_t now=millis(), elapsed=now-lastFlowWindowMs;
    if(elapsed<FLOW_WINDOW_MS) return;
    const uint32_t pulses=readFlowPulses(), deltaPulses=pulses-lastFlowSnapshot;
    lastFlowSnapshot=pulses; lastFlowWindowMs=now;
    measuredFlowLpm=elapsed>0
        ? static_cast<float>(deltaPulses)*60000.0f/(FLOW_PULSES_PER_LITRE*static_cast<float>(elapsed))
        : 0.0f;
    if (valveIsOpen && (now-valveOpenedAtMs>FLOW_FAULT_GRACE_MS) && measuredFlowLpm<MIN_FLOW_LPM)
        flowFaultLatched = true;
    flowFault = flowFaultLatched;
}

uint16_t minuteOfDay() {
    const uint32_t elapsed=(millis()-startupMs)/60000UL;
    return static_cast<uint16_t>((SENTINEL_START_MINUTE_OF_DAY+elapsed)%1440UL);
}

void runController() {
    sentinel::ControllerInput input{};
    input.minute_of_day=minuteOfDay();
    input.node_a_valid=nodeA.valid; input.node_b_valid=nodeB.valid;
    input.node_a_age_sec=nodeA.valid?(millis()-nodeA.last_rx_ms)/1000.0f:1.0e9f;
    input.node_b_age_sec=nodeB.valid?(millis()-nodeB.last_rx_ms)/1000.0f:1.0e9f;
    input.t_air_a_c=packetTemp(nodeA.packet.t_air_centi);
    input.rh_a_pct=packetValue(nodeA.packet.rh_centi);
    input.lws_a_pct=packetValue(nodeA.packet.lws_centi);
    input.vwc_b_pct=packetValue(nodeB.packet.vwc_centi);
    input.cwsi_b=sentinel::calculateCwsi(
        packetTemp(nodeB.packet.t_canopy_centi),
        packetTemp(nodeB.packet.t_air_centi),
        packetValue(nodeB.packet.rh_centi)
    );
    input.accumulated_dsv=accumulatedLwsDsv;
    input.continuous_lockout_hours = lockoutTimerActive
        ? (millis() - lockoutStartedMs) / 3600000.0f : 0.0f;
    input.flow_fault=flowFault;
    input.uncertainty_buffered=insufficientCoverage;
    const sentinel::ControllerOutput output=sentinel::evaluateController(input,thresholds);
    currentState=output.state;
    if (currentState == sentinel::ControllerState::PATHOGEN_LOCKOUT) {
        if (!lockoutTimerActive) { lockoutTimerActive = true; lockoutStartedMs = millis(); }
    } else {
        lockoutTimerActive = false;
        lockoutStartedMs = 0;
    }
    commandValve(output.valve_open);
    if(millis()-lastControllerLogMs>=10000UL){
        lastControllerLogMs=millis();
        Serial.printf("State=%u valve=%s A_age=%.0fs B_age=%.0fs CWSI=%.2f DSV=%u flow=%.3f L/min suff=%s diff=%.2f rs=%.2f\n",
            static_cast<unsigned>(currentState),valveIsOpen?"OPEN":"CLOSED",
            input.node_a_age_sec,input.node_b_age_sec,input.cwsi_b,input.accumulated_dsv,
            measuredFlowLpm,insufficientCoverage?"INSUFFICIENT":"OK",latestVwcDivergence,latestSpearman);
    }
}

void setup() {
    Serial.begin(115200);
    startupMs=millis();
    pinMode(PIN_VALVE_OPEN,OUTPUT); pinMode(PIN_VALVE_CLOSE,OUTPUT);
    digitalWrite(PIN_VALVE_OPEN,LOW); digitalWrite(PIN_VALVE_CLOSE,LOW);
    pinMode(PIN_FLOW_SENSOR,INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_FLOW_SENSOR),onFlowPulse,RISING);
    SPI.begin(PIN_LORA_SCK,PIN_LORA_MISO,PIN_LORA_MOSI,PIN_LORA_CS);
    radio.setDio2AsRfSwitch(true);
    const int16_t state=radio.begin(866.0,125.0,9,5,0x12,22,8,1.6,false);
    if(state!=RADIOLIB_ERR_NONE){
        Serial.printf("SX1262 init failed: %d; do not actuate\n",state);
        flowFault=true;
    } else radio.startReceive();
    lastFlowWindowMs=millis(); lastFlowSnapshot=readFlowPulses();
    monotonicDay=millis()/86400000UL;
}

void loop() {
    receiveLoRaPacket();
    updateSpatialSufficiency();
    updateFlowFault();
    serviceValveLatchPulse();
    runController();
    delay(5);
}
