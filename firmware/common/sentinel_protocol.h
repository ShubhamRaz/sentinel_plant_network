#pragma once
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace sentinel {

#pragma pack(push, 1)
struct SentinelPacket {
    uint8_t magic;           // 0xA5
    uint8_t node_id;         // 1=humid, 2=dry, 3=adaptive
    uint16_t seq_num;
    uint32_t uptime_sec;
    int16_t t_air_centi;
    uint16_t rh_centi;
    int16_t t_canopy_centi;
    uint16_t vwc_centi;
    uint16_t lws_centi;
    uint16_t vbat_mv;
    uint8_t status_flags;     // bit0 BME_OK, bit1 MLX_OK, bit2 LWS_WET, bit3 LOW_BAT
    uint8_t reserved;
    uint16_t crc16;
};
#pragma pack(pop)

static_assert(sizeof(SentinelPacket) == 24, "Protocol v2.0 packet must remain 24 bytes");

inline uint16_t crc16Ccitt(const uint8_t* data, size_t length) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < length; ++i) {
        crc ^= static_cast<uint16_t>(data[i]) << 8;
        for (uint8_t bit = 0; bit < 8; ++bit) {
            crc = (crc & 0x8000U) ? static_cast<uint16_t>((crc << 1) ^ 0x1021U)
                                  : static_cast<uint16_t>(crc << 1);
        }
    }
    return crc;
}

inline bool validatePacket(const uint8_t* bytes, size_t length, SentinelPacket& out) {
    if (bytes == nullptr || length != sizeof(SentinelPacket)) return false;
    SentinelPacket candidate{};
    for (size_t i = 0; i < sizeof(candidate); ++i) {
        reinterpret_cast<uint8_t*>(&candidate)[i] = bytes[i];
    }
    if (candidate.magic != 0xA5) return false;
    const auto expected = crc16Ccitt(bytes, sizeof(SentinelPacket) - sizeof(candidate.crc16));
    if (candidate.crc16 != expected) return false;
    if (candidate.node_id < 1 || candidate.node_id > 3) return false;
    out = candidate;
    return true;
}

enum class ControllerState : uint8_t {
    HOMEOSTASIS = 0,
    STANDARD_DRIP = 1,
    PATHOGEN_LOCKOUT = 2,
    CONFLICT_MICRO_PULSE = 3,
    EMERGENCY_DRIP = 4,
    FAULT_FALLBACK = 5
};

struct ControllerInput {
    uint16_t minute_of_day = 0;
    float node_a_age_sec = 1.0e9f;
    float node_b_age_sec = 1.0e9f;
    float t_air_a_c = NAN;
    float rh_a_pct = NAN;
    float lws_a_pct = NAN;
    float vwc_b_pct = NAN;
    float cwsi_b = NAN;
    uint16_t accumulated_dsv = 0;
    float continuous_lockout_hours = 0.0f;
    bool node_a_valid = false;
    bool node_b_valid = false;
    bool flow_fault = false;
    bool uncertainty_buffered = false;
};

struct ControllerOutput {
    ControllerState state;
    bool valve_open;
};

struct ProtocolThresholds {
    float cwsi_stress = 0.40f;
    float cwsi_emergency = 0.65f;
    float vwc_mad = 22.0f;
    float vwc_emergency = 16.0f;
    uint16_t dsv_action = 18;
    uint32_t stale_timeout_sec = 1800;
    float max_lockout_hours = 36.0f;
    uint16_t midday_start = 690;
    uint16_t midday_end = 870;
    uint16_t pulse_on_minutes = 15;
    uint16_t pulse_off_minutes = 45;
};

inline ControllerOutput evaluateController(
    const ControllerInput& in,
    const ProtocolThresholds& cfg = ProtocolThresholds{}
) {
    const bool invalid = !in.node_a_valid || !in.node_b_valid ||
        in.node_a_age_sec > cfg.stale_timeout_sec ||
        in.node_b_age_sec > cfg.stale_timeout_sec ||
        !std::isfinite(in.t_air_a_c) || !std::isfinite(in.rh_a_pct) ||
        !std::isfinite(in.lws_a_pct) || !std::isfinite(in.vwc_b_pct) ||
        !std::isfinite(in.cwsi_b) || in.minute_of_day >= 1440;
    if (invalid || in.flow_fault) return {ControllerState::FAULT_FALLBACK, false};

    if (in.cwsi_b >= cfg.cwsi_emergency || in.vwc_b_pct <= cfg.vwc_emergency)
        return {ControllerState::EMERGENCY_DRIP, true};

    const float mad = cfg.vwc_mad + (in.uncertainty_buffered ? 1.0f : 0.0f);
    const bool water_stress = in.cwsi_b >= cfg.cwsi_stress || in.vwc_b_pct <= mad;
    const bool blight_risk = in.accumulated_dsv >= cfg.dsv_action ||
        (in.rh_a_pct >= 90.0f && in.lws_a_pct >= 50.0f);
    const bool lockout_capped = in.continuous_lockout_hours >= cfg.max_lockout_hours;

    if (water_stress && (!blight_risk || lockout_capped))
        return {ControllerState::STANDARD_DRIP, true};

    if (water_stress && blight_risk && !lockout_capped) {
        if (in.minute_of_day >= cfg.midday_start && in.minute_of_day < cfg.midday_end) {
            const uint16_t period = cfg.pulse_on_minutes + cfg.pulse_off_minutes;
            const uint16_t offset = static_cast<uint16_t>((in.minute_of_day - cfg.midday_start) % period);
            return {ControllerState::CONFLICT_MICRO_PULSE, offset < cfg.pulse_on_minutes};
        }
        return {ControllerState::PATHOGEN_LOCKOUT, false};
    }
    if (!water_stress && blight_risk)
        return {ControllerState::PATHOGEN_LOCKOUT, false};
    return {ControllerState::HOMEOSTASIS, false};
}

inline float calculateVpdKpa(float temperature_c, float rh_pct) {
    const float rh = (rh_pct < 1.0f) ? 1.0f : ((rh_pct > 100.0f) ? 100.0f : rh_pct);
    const float es = 0.61078f * std::exp((17.27f * temperature_c) / (temperature_c + 237.3f));
    const float ea = es * rh / 100.0f;
    const float vpd = es - ea;
    return vpd < 0.05f ? 0.05f : vpd;
}

inline float calculateCwsi(float canopy_c, float air_c, float rh_pct) {
    if (!std::isfinite(canopy_c) || !std::isfinite(air_c) || !std::isfinite(rh_pct)) return NAN;
    const float vpd = calculateVpdKpa(air_c, rh_pct);
    const float lower = 1.35f - 1.95f * vpd;
    const float upper = 3.50f;
    const float denominator = (upper - lower) < 0.5f ? 0.5f : (upper - lower);
    float value = ((canopy_c - air_c) - lower) / denominator;
    if (value < 0.0f) value = 0.0f;
    if (value > 1.0f) value = 1.0f;
    return value;
}

}  // namespace sentinel
