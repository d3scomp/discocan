#ifndef __PUNCHPRESS_SIM_H__
#define __PUNCHPRESS_SIM_H__
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

#include "protocol.h"

void PunchPressSim_Init(void);
void PunchPressSim_MainStep();
void PunchPressSim_PosStep(void);
void PunchPressSim_ProcessRestartPacket(const SimulationRestart *packet);
void PunchPressSim_ProcessPunchRequest(bool punch_requested);

#ifdef __cplusplus
}
#endif

#endif /* __PUNCHPRESS_SIM_H__ */
