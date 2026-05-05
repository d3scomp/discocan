#ifndef __PROTOCOL_H__
#define __PROTOCOL_H__

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>

/* Protocol frame header bytes */
#define FRAME_HEADER_0 0xAA
#define FRAME_HEADER_1 0x55

/* CAN ID definitions */
#define ECHO_ID 0x020
#define PUNCHPRESS_STATUS_ID 0x200
#define PUNCHPRESS_PUNCH_ID  0x201

/* Packet types */
typedef enum {
  PACKET_TYPE_CAN_FRAME = 0x01,         /* CAN frame received from the bus */
  PACKET_TYPE_SIMULATION_RESTART = 0x02,
  PACKET_TYPE_SIMULATION_STATUS = 0x03,
  PACKET_TYPE_SIMULATION_PUNCH = 0x04,
  PACKET_TYPE_CAN_TX_FRAME = 0x05,      /* CAN frame the firmware put on the bus */
  PACKET_TYPE_COUNT
} PacketType;

/* CAN frame structure. timestamp_ms is filled in by the firmware from
 * HAL_GetTick() when sending to the host (so trace entries reflect
 * device-side timing); host→FW frames may leave it 0. */
typedef struct __attribute__((packed)) {
  uint32_t timestamp_ms;
  uint32_t arb_id;
  uint8_t  dlc;
  uint8_t  data[8];
} CanFrame;

typedef struct __attribute__((packed)) {
  int32_t x_100um;
  int32_t y_100um;
} SimulationRestart;

typedef struct __attribute__((packed)) {
  int32_t x_100um;
  int32_t y_100um;
  uint8_t status_bits;
} SimulationStatus;

typedef struct __attribute__((packed)) {
  int32_t x_100um;
  int32_t y_100um;
} SimulationPunch;

/* Generic packet structure */
typedef struct {
  PacketType type;
  union {
    CanFrame can_frame;
    SimulationRestart simulation_restart;
    SimulationStatus simulation_status;
    SimulationPunch simulation_punch;
  } data;
} Packet;

/* Payload sizes for each packet type (indexed by PacketType - 1) */
extern const uint8_t PACKET_PAYLOAD_SIZES[PACKET_TYPE_COUNT];

#ifdef __cplusplus
}
#endif

#endif /* __PROTOCOL_H__ */
