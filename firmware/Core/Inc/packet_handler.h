#ifndef __PACKET_HANDLER_H__
#define __PACKET_HANDLER_H__

#ifdef __cplusplus
extern "C" {
#endif

#include "protocol.h"

/**
  * @brief  Called when a valid packet is received from serial interface
  * @param  packet: Pointer to received packet
  * @retval None
  */
void PacketHandler_OnPacketReceived(const Packet *packet);

/**
  * @brief  Called when a CAN frame is received
  * @param  frame: Pointer to received CAN frame
  * @retval None
  */
void PacketHandler_OnCanFrameReceived(const CanFrame *frame);

#ifdef __cplusplus
}
#endif

#endif /* __PACKET_HANDLER_H__ */
