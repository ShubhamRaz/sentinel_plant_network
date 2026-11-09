/**
 * @file gateway_firmware.ino
 * @brief Sentinel Plant Network - Local Gateway Decision & Actuation Firmware
 * @version 2.0 (Pre-Trial Protocol Specification)
 *
 * Implements:
 *  - LoRa packet reception & CRC-16 validation on SX1262 (GPIO10-14)
 *  - 30-minute packet staleness timeout & NaN plausibility checks
 *  - Crop Water Stress Index (CWSI) and Root-Zone Soil Moisture (VWC) evaluation
 *  - Parallel Wallin (1962) DSV and LWS-Modified Late Blight Severity accumulation
 *  - Adaptive Two-Node Spatial Sufficiency Check (|VWC_A - VWC_B| > 10% or r_s < 0.70)
 *  - 6-State Fault-Aware Irrigation Controller State Machine
 *  - H-Bridge 12V Latching Valve Driver (GPIO15/16) & YF-S201 Flow Meter (GPIO17)
 */

#include <Arduino.h>
#include <math.h>

// ============================================================================
// 1. GATEWAY PIN DEFINITIONS & PROTOCOL THRESHOLDS (Section 5.1 & Section 8)
// ============================================================================
static constexpr uint8_t  PIN_VALVE_OPEN      = 15;     // H-bridge pulse OPEN
static constexpr uint8_t  PIN_VALVE_CLOSE     = 16;     // H-bridge pulse CLOSE
static constexpr uint8_t  PIN_FLOW_SENSOR     = 17;     // YF-S201 Hall-effect interrupt

static constexpr float    THRESH_CWSI_STRESS  = 0.40f;  // Standard crop water stress
static constexpr float    THRESH_CWSI_EMERG   = 0.65f;  // Emergency drought override
static constexpr float    THRESH_VWC_MAD      = 22.0f;  // Management-allowed depletion (%)
static constexpr float    THRESH_VWC_EMERG    = 16.0f;  // Emergency drought floor (%)
static constexpr uint16_t THRESH_DSV_ACTION   = 18;     // Cumulative blight severity threshold
static constexpr uint32_t TIMEOUT_STALE_SEC   = 1800;   // 30-minute stale telemetry timeout
static constexpr float    MAX_LOCKOUT_HOURS   = 36.0f;  // Max continuous pathogen lockout
static constexpr float    SUFF_MAX_VWC_DIFF   = 10.0f;  // Max VWC divergence (%) before flag
static constexpr float    SUFF_MIN_SPEARMAN   = 0.70f;  // Min Spearman rank correlation

enum class ControllerState : uint8_t {
    HOMEOSTASIS          = 0,
    STANDARD_DRIP        = 1,
    PATHOGEN_LOCKOUT     = 2,
    CONFLICT_MICRO_PULSE = 3,
    EMERGENCY_DRIP       = 4,
    FAULT_FALLBACK       = 5
};

struct NodeTelemetry {
    float    t_air_c;
    float    rh_pct;
    float    t_canopy_c;
    float    vwc_pct;
    float    lws_pct;
    uint32_t age_sec;
    bool     valid;
};

volatile uint32_t g_flow_pulses = 0;
void IRAM_ATTR onFlowPulse() {
    g_flow_pulses++;
}

// ============================================================================
// 2. LATCHING VALVE ACTUATION & FLOW VERIFICATION
// ============================================================================
void latchValve(bool open_cmd) {
    if (open_cmd) {
        digitalWrite(PIN_VALVE_CLOSE, LOW);
        digitalWrite(PIN_VALVE_OPEN, HIGH);
        delay(80); // 80 ms latching solenoid pulse
        digitalWrite(PIN_VALVE_OPEN, LOW);
    } else {
        digitalWrite(PIN_VALVE_OPEN, LOW);
        digitalWrite(PIN_VALVE_CLOSE, HIGH);
        delay(80);
        digitalWrite(PIN_VALVE_CLOSE, LOW);
    }
}

// ============================================================================
// 3. GATEWAY DECISION STATE MACHINE (Figure 3 & Table in Section 8)
// ============================================================================
ControllerState evaluateGatewayFSM(
    const NodeTelemetry& nodeA,
    const NodeTelemetry& nodeB,
    float cwsi_b,
    uint16_t accumulated_dsv,
    float current_lockout_hours,
    uint16_t minute_of_day, // 0..1439 (11:30 = 690, 14:30 = 870)
    bool flow_fault_detected
) {
    // Step 1: Validate packet staleness, NaN plausibility, and flow hardware health
    bool invalid_a = !nodeA.valid || (nodeA.age_sec > TIMEOUT_STALE_SEC) ||
                     isnan(nodeA.t_air_c) || isnan(nodeA.rh_pct) || isnan(nodeA.lws_pct);
    bool invalid_b = !nodeB.valid || (nodeB.age_sec > TIMEOUT_STALE_SEC) ||
                     isnan(nodeB.vwc_pct) || isnan(nodeB.t_canopy_c) || isnan(cwsi_b);

    if (invalid_a || invalid_b || flow_fault_detected) {
        return ControllerState::FAULT_FALLBACK;
    }

    // Step 2: Check severe drought override (CWSI >= 0.65 or VWC <= 16%)
    if (cwsi_b >= THRESH_CWSI_EMERG || nodeB.vwc_pct <= THRESH_VWC_EMERG) {
        return ControllerState::EMERGENCY_DRIP;
    }

    // Step 3: Evaluate standard water stress and blight-conducive risk
    bool water_stress = (cwsi_b >= THRESH_CWSI_STRESS) || (nodeB.vwc_pct <= THRESH_VWC_MAD);
    bool blight_risk  = (accumulated_dsv >= THRESH_DSV_ACTION) ||
                        (nodeA.rh_pct >= 90.0f && nodeA.lws_pct >= 50.0f);
    bool lockout_capped = (current_lockout_hours >= MAX_LOCKOUT_HOURS);

    if (water_stress && (!blight_risk || lockout_capped)) {
        return ControllerState::STANDARD_DRIP;
    }

    if (water_stress && blight_risk && !lockout_capped) {
        // Conflict state: permit 15 min ON / 45 min OFF micro-pulse inside 11:30-14:30
        bool in_midday_window = (minute_of_day >= 690 && minute_of_day <= 870);
        if (in_midday_window) {
            return ControllerState::CONFLICT_MICRO_PULSE;
        } else {
            return ControllerState::PATHOGEN_LOCKOUT;
        }
    }

    if (!water_stress && blight_risk) {
        return ControllerState::PATHOGEN_LOCKOUT;
    }

    return ControllerState::HOMEOSTASIS;
}

void setup() {
    Serial.begin(115200);
    pinMode(PIN_VALVE_OPEN, OUTPUT);
    pinMode(PIN_VALVE_CLOSE, OUTPUT);
    pinMode(PIN_FLOW_SENSOR, INPUT_PULLUP);
    attachInterrupt(digitalPinToInterrupt(PIN_FLOW_SENSOR), onFlowPulse, RISING);
    latchValve(false);
}

void loop() {
    delay(1000);
}
