#include "packet_handler.h"
#include "punchpress_sim.h"
#include "usbd_cdc_if.h"
#include "main.h"

#include <stdio.h>
#include <string.h>


/* Protocol payload sizes array */
const uint8_t PACKET_PAYLOAD_SIZES[PACKET_TYPE_COUNT] = {
  [PACKET_TYPE_CAN_FRAME] = sizeof(CanFrame),
  [PACKET_TYPE_SIMULATION_RESTART] = sizeof(SimulationRestart),
  [PACKET_TYPE_SIMULATION_STATUS] = sizeof(SimulationStatus),
  [PACKET_TYPE_SIMULATION_PUNCH] = sizeof(SimulationPunch),
  [PACKET_TYPE_CAN_TX_FRAME] = sizeof(CanFrame),
};

/* External CAN handle */
extern CAN_HandleTypeDef hcan1;

/**
  * @brief  Called when a valid packet is received from serial interface
  * @param  packet: Pointer to received packet
  * @retval None
  */
void PacketHandler_OnPacketReceived(const Packet *packet)
{
  HAL_GPIO_TogglePin(HEARTBEAT_2_GPIO_Port, HEARTBEAT_2_Pin);

  if (packet->type == PACKET_TYPE_CAN_FRAME)
  {
    const CanFrame *frame = &packet->data.can_frame;

    /* Validate CAN frame parameters */
    if (frame->arb_id <= 0x7FF || frame->dlc <= 8) {
      /* Prepare CAN TX header */
      CAN_TxHeaderTypeDef txHeader;
      txHeader.StdId = frame->arb_id;
      txHeader.ExtId = 0;
      txHeader.IDE = CAN_ID_STD;
      txHeader.RTR = CAN_RTR_DATA;
      txHeader.DLC = frame->dlc;
      txHeader.TransmitGlobalTime = DISABLE;

      /* Transmit CAN message */
      uint32_t txMailbox;
      if (HAL_CAN_AddTxMessage(&hcan1, &txHeader, (uint8_t *)frame->data, &txMailbox) == HAL_OK)
      {
        /* Mirror the TX back to the host as a confirmation. The host treats
         * this CAN_TX_FRAME as the canonical "frame went on the bus" event,
         * so all tx trace entries originate here in one place. */
        Packet tx_pkt;
        tx_pkt.type = PACKET_TYPE_CAN_TX_FRAME;
        tx_pkt.data.can_frame = *frame;
        tx_pkt.data.can_frame.timestamp_ms = HAL_GetTick();
        CDC_TransmitPacket(&tx_pkt);
      }
    }
  }
  else if (packet->type == PACKET_TYPE_SIMULATION_RESTART)
  {
    PunchPressSim_ProcessRestartPacket(&packet->data.simulation_restart);
  }

  HAL_GPIO_TogglePin(HEARTBEAT_2_GPIO_Port, HEARTBEAT_2_Pin);
}

/**
  * @brief  Called when a CAN frame is received
  * @param  frame: Pointer to received CAN frame
  * @retval None
  */
void PacketHandler_OnCanFrameReceived(const CanFrame *frame)
{
  HAL_GPIO_TogglePin(HEARTBEAT_3_GPIO_Port, HEARTBEAT_3_Pin);

  /* Send the rx frame to the host first, before any reply we might generate
   * below (echo, etc.). This keeps the host trace ordered the same way the
   * frames actually appeared on the bus. */
  Packet packet;
  packet.type = PACKET_TYPE_CAN_FRAME;
  packet.data.can_frame = *frame;
  packet.data.can_frame.timestamp_ms = HAL_GetTick();
  CDC_TransmitPacket(&packet);

  if ((frame->arb_id == PUNCHPRESS_PUNCH_ID) && (frame->dlc == 1U))
  {
    bool punch_requested = frame->data[0] != 0;
    PunchPressSim_ProcessPunchRequest(punch_requested);
  }

  /* Echo handler: if received on ECHO_ID, reply on ECHO_ID + 1 with same payload */
  if (frame->arb_id == ECHO_ID)
  {
    CAN_TxHeaderTypeDef txHeader;
    txHeader.StdId = ECHO_ID + 1;
    txHeader.ExtId = 0;
    txHeader.IDE = CAN_ID_STD;
    txHeader.RTR = CAN_RTR_DATA;
    txHeader.DLC = frame->dlc;
    txHeader.TransmitGlobalTime = DISABLE;

    uint32_t txMailbox;
    if (HAL_CAN_AddTxMessage(&hcan1, &txHeader, (uint8_t *)frame->data, &txMailbox) == HAL_OK)
    {
      printf("ECHO: ID=0x%03lX -> 0x%03lX DLC=%u\n",
             (uint32_t)ECHO_ID, (uint32_t)(ECHO_ID + 1), frame->dlc);

      /* Mirror the TX to the host so the trace reflects what is on the wire. */
      Packet tx_pkt;
      tx_pkt.type = PACKET_TYPE_CAN_TX_FRAME;
      tx_pkt.data.can_frame.timestamp_ms = HAL_GetTick();
      tx_pkt.data.can_frame.arb_id = ECHO_ID + 1;
      tx_pkt.data.can_frame.dlc = frame->dlc;
      memcpy(tx_pkt.data.can_frame.data, frame->data, 8);
      CDC_TransmitPacket(&tx_pkt);
    }
  }

  HAL_GPIO_TogglePin(HEARTBEAT_3_GPIO_Port, HEARTBEAT_3_Pin);
}
