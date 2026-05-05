/* USER CODE BEGIN Header */
/**
 ******************************************************************************
 * @file           : usbd_cdc_if.c
 * @version        : v1.0_Cube
 * @brief          : Usb device for Virtual Com Port.
 ******************************************************************************
 * @attention
 *
 * Copyright (c) 2026 STMicroelectronics.
 * All rights reserved.
 *
 * This software is licensed under terms that can be found in the LICENSE file
 * in the root directory of this software component.
 * If no LICENSE file comes with this software, it is provided AS-IS.
 *
 ******************************************************************************
 */
/* USER CODE END Header */

/* Includes ------------------------------------------------------------------*/
#include "usbd_cdc_if.h"

/* USER CODE BEGIN INCLUDE */
#include "main.h"
#include "packet_handler.h"
#include <stdio.h>
#include <string.h>
/* USER CODE END INCLUDE */

/* Private typedef -----------------------------------------------------------*/
/* Private define ------------------------------------------------------------*/
/* Private macro -------------------------------------------------------------*/

/* USER CODE BEGIN PV */
/* Private variables ---------------------------------------------------------*/

/* USER CODE END PV */

/** @addtogroup STM32_USB_OTG_DEVICE_LIBRARY
  * @brief Usb device library.
  * @{
  */

/** @addtogroup USBD_CDC_IF
  * @{
  */

/** @defgroup USBD_CDC_IF_Private_TypesDefinitions USBD_CDC_IF_Private_TypesDefinitions
  * @brief Private types.
  * @{
  */

/* USER CODE BEGIN PRIVATE_TYPES */

/* USER CODE END PRIVATE_TYPES */

/**
  * @}
  */

/** @defgroup USBD_CDC_IF_Private_Defines USBD_CDC_IF_Private_Defines
  * @brief Private defines.
  * @{
  */

/* USER CODE BEGIN PRIVATE_DEFINES */
#define MAX_PAYLOAD_SIZE 17 /* Maximum payload size for any packet type (CanFrame = 4+4+1+8) */
#define SERIAL_PACKET_MAX_SIZE                                                 \
  (2 + 1 + MAX_PAYLOAD_SIZE +                                                  \
   4) /* header(2) + type(1) + payload(max) + crc32(4) */
/* USER CODE END PRIVATE_DEFINES */

/**
  * @}
  */

/** @defgroup USBD_CDC_IF_Private_Macros USBD_CDC_IF_Private_Macros
  * @brief Private macros.
  * @{
  */

/* USER CODE BEGIN PRIVATE_MACRO */

/* USER CODE END PRIVATE_MACRO */

/**
  * @}
  */

/** @defgroup USBD_CDC_IF_Private_Variables USBD_CDC_IF_Private_Variables
  * @brief Private variables.
  * @{
  */
/* Create buffer for reception and transmission           */
/* It's up to user to redefine and/or remove those define */
/** Received data over USB are stored in this buffer      */
uint8_t UserRxBufferFS[APP_RX_DATA_SIZE];

/** Data to send over USB CDC are stored in this buffer   */
uint8_t UserTxBufferFS[APP_TX_DATA_SIZE];

/* USER CODE BEGIN PRIVATE_VARIABLES */
/* Packet reception state machine */
typedef enum {
  RX_STATE_SYNC_0,  /* Waiting for 0xAA */
  RX_STATE_SYNC_1,  /* Waiting for 0x55 */
  RX_STATE_TYPE,    /* Waiting for packet type */
  RX_STATE_PAYLOAD, /* Receiving payload */
  RX_STATE_CRC      /* Receiving CRC32 */
} RxState;

static RxState rxState = RX_STATE_SYNC_0;
static PacketType rxPacketType;
static uint8_t rxPayloadBuf[MAX_PAYLOAD_SIZE];
static uint8_t rxPayloadSize;
static uint32_t rxBufIdx = 0;
static uint8_t rxCrcBuf[4];

/* Packet transmission queue */
#define TX_QUEUE_SIZE 8
typedef struct {
  uint8_t buffer[SERIAL_PACKET_MAX_SIZE];
  uint16_t length;
} TxQueueEntry;

static TxQueueEntry txQueue[TX_QUEUE_SIZE];
static volatile uint8_t txQueueHead = 0;
static volatile uint8_t txQueueTail = 0;
static volatile uint8_t txQueueCount = 0;

extern CRC_HandleTypeDef hcrc;

static uint32_t compute_packet_crc32(PacketType packet_type, const uint8_t *data, uint32_t len) {
  uint32_t words = len / 4;
  uint32_t remainder = len % 4;

  __HAL_CRC_DR_RESET(&hcrc);
  /* RESET bit is set by software for one cycle and cleared by hardware once
   * DR has been reloaded with 0xFFFFFFFF. Without this poll, the very next
   * DR write races with the reset and is silently dropped. */
  while (hcrc.Instance->CR & CRC_CR_RESET) { /* wait */ }

  uint32_t packet_type_u32 = packet_type;
  hcrc.Instance->DR = __REV(packet_type_u32);

  const uint32_t *p32 = (const uint32_t *)data;
  for (uint32_t i = 0; i < words; i++) {
    hcrc.Instance->DR = __REV(p32[i]);
  }

  if (remainder) {
    uint32_t last = 0;
    memcpy(&last, &data[words * 4], remainder);
    hcrc.Instance->DR = __REV(last);
  }

  uint32_t crc = hcrc.Instance->DR;
  return crc;
}
/* USER CODE END PRIVATE_VARIABLES */

/**
  * @}
  */

/** @defgroup USBD_CDC_IF_Exported_Variables USBD_CDC_IF_Exported_Variables
  * @brief Public variables.
  * @{
  */

extern USBD_HandleTypeDef hUsbDeviceFS;

/* USER CODE BEGIN EXPORTED_VARIABLES */

/* USER CODE END EXPORTED_VARIABLES */

/**
  * @}
  */

/** @defgroup USBD_CDC_IF_Private_FunctionPrototypes USBD_CDC_IF_Private_FunctionPrototypes
  * @brief Private functions declaration.
  * @{
  */

static int8_t CDC_Init_FS(void);
static int8_t CDC_DeInit_FS(void);
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t* pbuf, uint16_t length);
static int8_t CDC_Receive_FS(uint8_t* pbuf, uint32_t *Len);
static int8_t CDC_TransmitCplt_FS(uint8_t *pbuf, uint32_t *Len, uint8_t epnum);

/* USER CODE BEGIN PRIVATE_FUNCTIONS_DECLARATION */
static void CDC_TrySendFromQueue(void);
/* USER CODE END PRIVATE_FUNCTIONS_DECLARATION */

/**
  * @}
  */

USBD_CDC_ItfTypeDef USBD_Interface_fops_FS =
{
  CDC_Init_FS,
  CDC_DeInit_FS,
  CDC_Control_FS,
  CDC_Receive_FS,
  CDC_TransmitCplt_FS
};

/* Private functions ---------------------------------------------------------*/
/**
  * @brief  Initializes the CDC media low layer over the FS USB IP
  * @retval USBD_OK if all operations are OK else USBD_FAIL
  */
static int8_t CDC_Init_FS(void)
{
  /* USER CODE BEGIN 3 */
  /* Set Application Buffers */
  USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, 0);
  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
  return (USBD_OK);
  /* USER CODE END 3 */
}

/**
  * @brief  DeInitializes the CDC media low layer
  * @retval USBD_OK if all operations are OK else USBD_FAIL
  */
static int8_t CDC_DeInit_FS(void)
{
  /* USER CODE BEGIN 4 */
  return (USBD_OK);
  /* USER CODE END 4 */
}

/**
  * @brief  Manage the CDC class requests
  * @param  cmd: Command code
  * @param  pbuf: Buffer containing command data (request parameters)
  * @param  length: Number of data to be sent (in bytes)
  * @retval Result of the operation: USBD_OK if all operations are OK else USBD_FAIL
  */
static int8_t CDC_Control_FS(uint8_t cmd, uint8_t* pbuf, uint16_t length)
{
  /* USER CODE BEGIN 5 */
  switch (cmd) {
  case CDC_SEND_ENCAPSULATED_COMMAND:

    break;

  case CDC_GET_ENCAPSULATED_RESPONSE:

    break;

  case CDC_SET_COMM_FEATURE:

    break;

  case CDC_GET_COMM_FEATURE:

    break;

  case CDC_CLEAR_COMM_FEATURE:

    break;

    /*******************************************************************************/
    /* Line Coding Structure */
    /*-----------------------------------------------------------------------------*/
    /* Offset | Field       | Size | Value  | Description */
    /* 0      | dwDTERate   |   4  | Number |Data terminal rate, in bits per
     * second*/
    /* 4      | bCharFormat |   1  | Number | Stop bits */
    /*                                        0 - 1 Stop bit */
    /*                                        1 - 1.5 Stop bits */
    /*                                        2 - 2 Stop bits */
    /* 5      | bParityType |  1   | Number | Parity */
    /*                                        0 - None */
    /*                                        1 - Odd */
    /*                                        2 - Even */
    /*                                        3 - Mark */
    /*                                        4 - Space */
    /* 6      | bDataBits  |   1   | Number Data bits (5, 6, 7, 8 or 16). */
    /*******************************************************************************/
  case CDC_SET_LINE_CODING:

    break;

  case CDC_GET_LINE_CODING:

    break;

  case CDC_SET_CONTROL_LINE_STATE:

    break;

  case CDC_SEND_BREAK:

    break;

  default:
    break;
  }

  return (USBD_OK);
  /* USER CODE END 5 */
}

/**
  * @brief  Data received over USB OUT endpoint are sent over CDC interface
  *         through this function.
  *
  *         @note
  *         This function will issue a NAK packet on any OUT packet received on
  *         USB endpoint until exiting this function. If you exit this function
  *         before transfer is complete on CDC interface (ie. using DMA controller)
  *         it will result in receiving more data while previous ones are still
  *         not sent.
  *
  * @param  Buf: Buffer of data to be received
  * @param  Len: Number of data received (in bytes)
  * @retval Result of the operation: USBD_OK if all operations are OK else USBD_FAIL
  */
static int8_t CDC_Receive_FS(uint8_t* Buf, uint32_t *Len)
{
  /* USER CODE BEGIN 6 */
  uint32_t len = *Len;

  for (uint32_t i = 0; i < len; i++) {
    uint8_t byte = Buf[i];

    switch (rxState) {
    case RX_STATE_SYNC_0:
      if (byte == FRAME_HEADER_0)
        rxState = RX_STATE_SYNC_1;
      break;

    case RX_STATE_SYNC_1:
      if (byte == FRAME_HEADER_1) {
        rxState = RX_STATE_TYPE;
      } else if (byte == FRAME_HEADER_0) {
        /* Stay in SYNC_1, could be repeated 0xAA */
        rxState = RX_STATE_SYNC_1;
      } else {
        rxState = RX_STATE_SYNC_0;
      }
      break;

    case RX_STATE_TYPE:
      /* Validate packet type */
      if (byte > 0 && byte < PACKET_TYPE_COUNT) {
        rxPacketType = (PacketType)byte;
        rxPayloadSize = PACKET_PAYLOAD_SIZES[rxPacketType];
        rxBufIdx = 0;
        rxState = RX_STATE_PAYLOAD;
      } else {
        /* Invalid packet type */
        rxState = RX_STATE_SYNC_0;
      }
      break;

    case RX_STATE_PAYLOAD:
      rxPayloadBuf[rxBufIdx++] = byte;
      if (rxBufIdx >= rxPayloadSize) {
        rxBufIdx = 0;
        rxState = RX_STATE_CRC;
      }
      break;

    case RX_STATE_CRC:
      rxCrcBuf[rxBufIdx++] = byte;
      if (rxBufIdx >= 4) {
        /* Complete packet received, verify CRC */
        uint32_t rxCrc;
        memcpy(&rxCrc, rxCrcBuf, sizeof(rxCrc));
        uint32_t calcCrc = compute_packet_crc32(rxPacketType, rxPayloadBuf, rxPayloadSize);

        if (rxCrc == calcCrc) {
          /* CRC valid, parse packet and call handler */
          Packet packet;
          packet.type = rxPacketType;

          /* Copy payload into appropriate union member */
          switch (rxPacketType) {
          case PACKET_TYPE_CAN_FRAME:
            memcpy(&packet.data.can_frame, rxPayloadBuf, sizeof(CanFrame));
            break;
          case PACKET_TYPE_SIMULATION_RESTART:
            memcpy(&packet.data.simulation_restart, rxPayloadBuf, sizeof(SimulationRestart));
            break;
          case PACKET_TYPE_SIMULATION_STATUS:
            memcpy(&packet.data.simulation_status, rxPayloadBuf, sizeof(SimulationStatus));
            break;
          case PACKET_TYPE_SIMULATION_PUNCH:
            memcpy(&packet.data.simulation_punch, rxPayloadBuf, sizeof(SimulationPunch));
            break;
          default:
            break;
          }

          /* Call packet handler */
          PacketHandler_OnPacketReceived(&packet);
        }

        /* Reset state machine */
        rxState = RX_STATE_SYNC_0;
        rxBufIdx = 0;
      }
      break;

    default:
      rxState = RX_STATE_SYNC_0;
      break;
    }
  }

  USBD_CDC_SetRxBuffer(&hUsbDeviceFS, &Buf[0]);
  USBD_CDC_ReceivePacket(&hUsbDeviceFS);
  return (USBD_OK);
  /* USER CODE END 6 */
}

/**
  * @brief  CDC_Transmit_FS
  *         Data to send over USB IN endpoint are sent over CDC interface
  *         through this function.
  *         @note
  *
  *
  * @param  Buf: Buffer of data to be sent
  * @param  Len: Number of data to be sent (in bytes)
  * @retval USBD_OK if all operations are OK else USBD_FAIL or USBD_BUSY
  */
uint8_t CDC_Transmit_FS(uint8_t* Buf, uint16_t Len)
{
  uint8_t result = USBD_OK;
  /* USER CODE BEGIN 7 */
  /* Not implemented - use CDC_TransmitPacket instead */
  (void)Buf;
  (void)Len;
  /* USER CODE END 7 */
  return result;
}

/**
  * @brief  CDC_TransmitCplt_FS
  *         Data transmitted callback
  *
  *         @note
  *         This function is IN transfer complete callback used to inform user that
  *         the submitted Data is successfully sent over USB.
  *
  * @param  Buf: Buffer of data to be received
  * @param  Len: Number of data received (in bytes)
  * @retval Result of the operation: USBD_OK if all operations are OK else USBD_FAIL
  */
static int8_t CDC_TransmitCplt_FS(uint8_t *Buf, uint32_t *Len, uint8_t epnum)
{
  uint8_t result = USBD_OK;
  /* USER CODE BEGIN 13 */
  UNUSED(Buf);
  UNUSED(Len);
  UNUSED(epnum);

  /* Try to send next packet from queue */
  // All interrupts have the same pre-emption priority, so the interrupts are
  // effectively disabled here.
  CDC_TrySendFromQueue();
  /* USER CODE END 13 */
  return result;
}

/* USER CODE BEGIN PRIVATE_FUNCTIONS_IMPLEMENTATION */

/**
 * @brief  Try to send next packet(s) from queue
 * @retval None
 */
static void CDC_TrySendFromQueue(void) {
  /* Guard against pre-enumeration NULL deref: pClassData is only populated
   * after host SET_CONFIGURATION. */
  if (hUsbDeviceFS.pClassData == NULL) {
    return;
  }

  USBD_CDC_HandleTypeDef *hcdc =
      (USBD_CDC_HandleTypeDef *)hUsbDeviceFS.pClassData;

  /* If CDC is busy or queue is empty, do nothing */
  if (hcdc->TxState != 0 || txQueueCount == 0) {
    return;
  }

  /* Pack as many packets as possible into UserTxBufferFS */
  uint16_t totalLength = 0;
  uint8_t packetsSent = 0;
  uint8_t queueIdx = txQueueHead;

  while (txQueueCount > packetsSent &&
         totalLength + txQueue[queueIdx].length <= APP_TX_DATA_SIZE) {
    TxQueueEntry *entry = &txQueue[queueIdx];

    /* Copy packet to UserTxBufferFS */
    memcpy(&UserTxBufferFS[totalLength], entry->buffer, entry->length);
    totalLength += entry->length;
    packetsSent++;

    queueIdx = (queueIdx + 1) % TX_QUEUE_SIZE;
  }

  /* If we have at least one packet to send, transmit */
  if (packetsSent > 0) {
    USBD_CDC_SetTxBuffer(&hUsbDeviceFS, UserTxBufferFS, totalLength);
    USBD_CDC_TransmitPacket(&hUsbDeviceFS);

    /* Update queue head and count */
    txQueueHead = queueIdx;
    txQueueCount -= packetsSent;
  }
}

/**
 * @brief  Transmit a packet over USB CDC
 * @param  packet: Pointer to packet to transmit
 * @retval USBD_OK if all operations are OK else USBD_FAIL or USBD_BUSY
 */
uint8_t CDC_TransmitPacket(const Packet *packet) {
  /* Validate packet type */
  if (packet->type <= 0 || packet->type >= PACKET_TYPE_COUNT) {
    return USBD_FAIL;
  }

  uint8_t payloadSize = PACKET_PAYLOAD_SIZES[packet->type];

  /* Get payload pointer */
  const uint8_t *payloadPtr = (const uint8_t *)&packet->data;

  /* Critical section - CDC_TransmitPacket may be called from main and interrupt
   */
  __disable_irq();

  /* If the queue is full, give it a chance to drain. Without this, packets
   * that piled up before USB enumeration completed (e.g. CAN burst at boot)
   * stay queued forever — nothing else triggers TrySendFromQueue once the
   * host enumerates. */
  if (txQueueCount >= TX_QUEUE_SIZE) {
    CDC_TrySendFromQueue();
    if (txQueueCount >= TX_QUEUE_SIZE) {
      __enable_irq();
      return USBD_BUSY;
    }
  }

  /* Build packet in queue entry */
  TxQueueEntry *entry = &txQueue[txQueueTail];
  uint8_t idx = 0;

  /* Header */
  entry->buffer[idx++] = FRAME_HEADER_0;
  entry->buffer[idx++] = FRAME_HEADER_1;

  /* Packet type */
  entry->buffer[idx++] = (uint8_t)packet->type;

  /* Payload */
  memcpy(&entry->buffer[idx], payloadPtr, payloadSize);
  idx += payloadSize;

  /* CRC32 over payload */
  uint32_t crc = compute_packet_crc32(packet->type, payloadPtr, payloadSize);
  memcpy(&entry->buffer[idx], &crc, sizeof(crc));
  idx += sizeof(crc);

  entry->length = idx;

  /* Critical section - add to queue */
  txQueueTail = (txQueueTail + 1) % TX_QUEUE_SIZE;
  txQueueCount++;

  /* Try to send immediately if CDC is not busy */
  CDC_TrySendFromQueue();

  __enable_irq();

  return USBD_OK;
}

/* USER CODE END PRIVATE_FUNCTIONS_IMPLEMENTATION */

/**
  * @}
  */

/**
  * @}
  */
