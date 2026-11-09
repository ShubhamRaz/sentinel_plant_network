#include <cassert>
#include <cmath>
#include <cstdint>
#include "../firmware/common/sentinel_protocol.h"
using namespace sentinel;

static ControllerInput healthyInput() {
    ControllerInput in{};
    in.minute_of_day=600; in.node_a_age_sec=1; in.node_b_age_sec=1;
    in.t_air_a_c=20; in.rh_a_pct=60; in.lws_a_pct=10;
    in.vwc_b_pct=28; in.cwsi_b=0.2f;
    in.node_a_valid=true; in.node_b_valid=true;
    return in;
}
int main() {
    static_assert(sizeof(SentinelPacket)==24, "packet size regression");
    const uint8_t check[]={'1','2','3','4','5','6','7','8','9'};
    assert(crc16Ccitt(check,sizeof(check))==0x29B1);
    SentinelPacket packet{}; packet.magic=0xA5; packet.node_id=1;
    packet.crc16=crc16Ccitt(reinterpret_cast<const uint8_t*>(&packet),sizeof(packet)-2);
    SentinelPacket decoded{};
    assert(validatePacket(reinterpret_cast<const uint8_t*>(&packet),sizeof(packet),decoded));
    packet.crc16^=1;
    assert(!validatePacket(reinterpret_cast<const uint8_t*>(&packet),sizeof(packet),decoded));
    assert(!validatePacket(reinterpret_cast<const uint8_t*>(&packet),sizeof(packet)-1,decoded));

    auto in=healthyInput();
    assert(evaluateController(in).state==ControllerState::HOMEOSTASIS);
    in=healthyInput(); in.cwsi_b=0.399f; in.vwc_b_pct=22.1f;
    assert(evaluateController(in).state==ControllerState::HOMEOSTASIS);
    in.cwsi_b=0.400f;
    assert(evaluateController(in).state==ControllerState::STANDARD_DRIP);
    in=healthyInput(); in.vwc_b_pct=22.0f;
    assert(evaluateController(in).state==ControllerState::STANDARD_DRIP);
    in=healthyInput(); in.cwsi_b=0.649f; in.vwc_b_pct=16.1f;
    assert(evaluateController(in).state==ControllerState::STANDARD_DRIP);
    in=healthyInput(); in.vwc_b_pct=16.0f;
    assert(evaluateController(in).state==ControllerState::EMERGENCY_DRIP);
    in=healthyInput(); in.cwsi_b=0.650f;
    assert(evaluateController(in).state==ControllerState::EMERGENCY_DRIP);

    in=healthyInput(); in.accumulated_dsv=18;
    assert(evaluateController(in).state==ControllerState::PATHOGEN_LOCKOUT);
    in=healthyInput(); in.rh_a_pct=90; in.lws_a_pct=50;
    assert(evaluateController(in).state==ControllerState::PATHOGEN_LOCKOUT);
    in.vwc_b_pct=21; in.minute_of_day=689;
    assert(evaluateController(in).state==ControllerState::PATHOGEN_LOCKOUT);
    in.continuous_lockout_hours=35.99f;
    assert(evaluateController(in).state==ControllerState::PATHOGEN_LOCKOUT);
    in.continuous_lockout_hours=36.0f;
    assert(evaluateController(in).state==ControllerState::STANDARD_DRIP);
    in.continuous_lockout_hours=0.0f;
    in.minute_of_day=690;
    auto on=evaluateController(in);
    assert(on.state==ControllerState::CONFLICT_MICRO_PULSE && on.valve_open);
    in.minute_of_day=705;
    auto off=evaluateController(in);
    assert(off.state==ControllerState::CONFLICT_MICRO_PULSE && !off.valve_open);
    in.minute_of_day=869;
    assert(evaluateController(in).state==ControllerState::CONFLICT_MICRO_PULSE);
    in.minute_of_day=870;
    assert(evaluateController(in).state==ControllerState::PATHOGEN_LOCKOUT);

    in=healthyInput(); in.node_a_age_sec=1801;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.node_b_age_sec=1801;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.flow_fault=true;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.node_a_valid=false;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.rh_a_pct=NAN;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.lws_a_pct=NAN;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.vwc_b_pct=NAN;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    in=healthyInput(); in.cwsi_b=NAN;
    assert(evaluateController(in).state==ControllerState::FAULT_FALLBACK);
    assert(std::isfinite(calculateCwsi(29,25,50)));
    assert(std::isnan(calculateCwsi(NAN,25,50)));
    return 0;
}
