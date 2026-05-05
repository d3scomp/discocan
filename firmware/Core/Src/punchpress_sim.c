#include "punchpress_sim.h"

#include "main.h"
#include "usbd_cdc_if.h"

#include <stdbool.h>
#include <stdio.h>
#include <string.h>

extern CAN_HandleTypeDef hcan1;
extern TIM_HandleTypeDef htim2;
extern TIM_HandleTypeDef htim3;
extern TIM_HandleTypeDef htim5;

#define PWM_COUNTER_MAX            1200000  // 20ms at 60MHz

#define WORK_AREA_WIDTH_MM         2000.0f
#define WORK_AREA_HEIGHT_MM        1500.0f
#define BORDER_ZONE_MM             100.0f
#define ENCODER_TICKS_PER_MM       10.0f
#define INPUT_GAIN_MM_PER_TICK2    0.00001f
#define INPUT_THRESHOLD            0.40f
#define SPEED_DRAG_1_PER_TICK      0.0002f
#define DYNAMIC_DRAG_MM_PER_TICK2  0.0000005f
#define STOP_SPEED_MM_PER_TICK     0.005f

#define STATUS_PERIOD_MS           100U
#define HEAD_RETRACT_TIME_MS       200U

#define STATUS_BIT_TOP_BORDER      (1U << 0)
#define STATUS_BIT_BOTTOM_BORDER   (1U << 1)
#define STATUS_BIT_LEFT_BORDER     (1U << 2)
#define STATUS_BIT_RIGHT_BORDER    (1U << 3)
#define STATUS_BIT_HEAD_UP         (1U << 4)
#define STATUS_BIT_FAIL            (1U << 5)

volatile static float sim_x_pos_mm;
volatile static float sim_x_speed_mm_per_tick;
volatile static float sim_x_input;

volatile static float sim_y_pos_mm;
volatile static float sim_y_speed_mm_per_tick;
volatile static float sim_y_input;

volatile static bool sim_fail;
volatile static bool sim_border_top;
volatile static bool sim_border_bottom;
volatile static bool sim_border_left;
volatile static bool sim_border_right;

volatile static bool sim_head_up;
volatile static bool sim_punch_requested;
volatile static uint32_t sim_head_retract_at_ms;
volatile static uint32_t sim_next_status_tick_ms;

static const GPIO_PinState sim_quadrature_sequence_a[4] = {GPIO_PIN_RESET, GPIO_PIN_SET, GPIO_PIN_SET, GPIO_PIN_RESET};
static const GPIO_PinState sim_quadrature_sequence_b[4] = {GPIO_PIN_RESET, GPIO_PIN_RESET, GPIO_PIN_SET, GPIO_PIN_SET};


static float sim_absf(float value)
{
  return (value < 0.0f) ? -value : value;
}

static float sim_signf(float value)
{
  if (value > 0.0f)
  {
    return 1.0f;
  }

  if (value < 0.0f)
  {
    return -1.0f;
  }

  return 0.0f;
}

static float sim_clampf(float value, float min_value, float max_value)
{
  if (value < min_value)
  {
    return min_value;
  }

  if (value > max_value)
  {
    return max_value;
  }

  return value;
}

static void sim_update_status_flags(void) {
  if (sim_x_pos_mm < 0.0f || sim_x_pos_mm > WORK_AREA_WIDTH_MM + BORDER_ZONE_MM*2 || sim_y_pos_mm < 0.0f || sim_y_pos_mm > WORK_AREA_HEIGHT_MM + BORDER_ZONE_MM*2) {
    sim_fail = true;
  }

  sim_border_bottom = sim_y_pos_mm < BORDER_ZONE_MM;
  sim_border_top = sim_y_pos_mm > WORK_AREA_HEIGHT_MM + BORDER_ZONE_MM;
  sim_border_left = sim_x_pos_mm < BORDER_ZONE_MM;
  sim_border_right = sim_x_pos_mm > WORK_AREA_WIDTH_MM + BORDER_ZONE_MM;
}

static uint8_t sim_get_status_bits(void)
{
  uint8_t bits = 0;

  if (sim_border_top)
  {
    bits |= STATUS_BIT_TOP_BORDER;
  }
  if (sim_border_bottom)
  {
    bits |= STATUS_BIT_BOTTOM_BORDER;
  }
  if (sim_border_left)
  {
    bits |= STATUS_BIT_LEFT_BORDER;
  }
  if (sim_border_right)
  {
    bits |= STATUS_BIT_RIGHT_BORDER;
  }
  if (sim_head_up && !sim_punch_requested)
  {
    bits |= STATUS_BIT_HEAD_UP;
  }
  if (sim_fail)
  {
    bits |= STATUS_BIT_FAIL;
  }

  return bits;
}

static void sim_send_status(void)
{
  uint8_t status_bits = sim_get_status_bits();

  Packet packet;
  packet.type = PACKET_TYPE_SIMULATION_STATUS;
  packet.data.simulation_status.x_100um = (int32_t)(sim_x_pos_mm * 100.0f);
  packet.data.simulation_status.y_100um = (int32_t)(sim_y_pos_mm * 100.0f);
  packet.data.simulation_status.status_bits = status_bits;
  CDC_TransmitPacket(&packet);

  CAN_TxHeaderTypeDef txHeader;
  txHeader.StdId = PUNCHPRESS_STATUS_ID;
  txHeader.ExtId = 0;
  txHeader.IDE = CAN_ID_STD;
  txHeader.RTR = CAN_RTR_DATA;
  txHeader.DLC = 1U;
  txHeader.TransmitGlobalTime = DISABLE;

  uint32_t txMailbox;
  uint8_t payload[8] = {status_bits, 0, 0, 0, 0, 0, 0, 0};
  if (HAL_CAN_AddTxMessage(&hcan1, &txHeader, payload, &txMailbox) == HAL_OK)
  {
    /* Mirror the TX to the host so the trace reflects what is on the wire. */
    Packet tx_pkt;
    tx_pkt.type = PACKET_TYPE_CAN_TX_FRAME;
    tx_pkt.data.can_frame.timestamp_ms = HAL_GetTick();
    tx_pkt.data.can_frame.arb_id = PUNCHPRESS_STATUS_ID;
    tx_pkt.data.can_frame.dlc = 1;
    memcpy(tx_pkt.data.can_frame.data, payload, 8);
    CDC_TransmitPacket(&tx_pkt);
  }
}

static void sim_send_punch(void)
{
  Packet packet;

  packet.type = PACKET_TYPE_SIMULATION_PUNCH;
  packet.data.simulation_punch.x_100um = (int32_t)(sim_x_pos_mm * 100.0f);
  packet.data.simulation_punch.y_100um = (int32_t)(sim_y_pos_mm * 100.0f);
  CDC_TransmitPacket(&packet);
}

static float sim_read_axis_command(TIM_HandleTypeDef *timer, uint32_t period_channel, uint32_t pulse_channel)
{
  uint32_t period = HAL_TIM_ReadCapturedValue(timer, period_channel);
  uint32_t pulse = HAL_TIM_ReadCapturedValue(timer, pulse_channel);
  uint32_t counter = __HAL_TIM_GET_COUNTER(timer);

  if (period == 0 || pulse > period || counter > PWM_COUNTER_MAX) {
    return 0.0f;
  }

  float duty = ((float)pulse / (float)period) * 2.2f - 1.1f;
  duty = sim_clampf(duty, -1.0f, 1.0f);

  return duty;
}

static void sim_output_enc(void) {
  int32_t x_enc = (int32_t)(sim_x_pos_mm * ENCODER_TICKS_PER_MM);
  int32_t y_enc = (int32_t)(sim_y_pos_mm * ENCODER_TICKS_PER_MM);

  HAL_GPIO_WritePin(ENC_X_A_GPIO_Port, ENC_X_A_Pin, sim_quadrature_sequence_a[x_enc & 0x03U]);
  HAL_GPIO_WritePin(ENC_X_B_GPIO_Port, ENC_X_B_Pin, sim_quadrature_sequence_b[x_enc & 0x03U]);

  HAL_GPIO_WritePin(ENC_Y_A_GPIO_Port, ENC_Y_A_Pin, sim_quadrature_sequence_a[y_enc & 0x03U]);
  HAL_GPIO_WritePin(ENC_Y_B_GPIO_Port, ENC_Y_B_Pin, sim_quadrature_sequence_b[y_enc & 0x03U]);
}

static void sim_output_border(void) {
  HAL_GPIO_WritePin(BORDER_LEFT_GPIO_Port, BORDER_LEFT_Pin, sim_border_left ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(BORDER_RIGHT_GPIO_Port, BORDER_RIGHT_Pin, sim_border_right ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(BORDER_BOTTOM_GPIO_Port, BORDER_BOTTOM_Pin, sim_border_bottom ? GPIO_PIN_SET : GPIO_PIN_RESET);
  HAL_GPIO_WritePin(BORDER_TOP_GPIO_Port, BORDER_TOP_Pin, sim_border_top ? GPIO_PIN_SET : GPIO_PIN_RESET);
}

static void sim_reset(float x_pos_mm, float y_pos_mm) {
  __disable_irq();
  sim_x_pos_mm = x_pos_mm;
  sim_y_pos_mm = y_pos_mm;
  sim_x_speed_mm_per_tick = 0.0f;
  sim_y_speed_mm_per_tick = 0.0f;
  sim_x_input = 0.0f;
  sim_y_input = 0.0f;
  sim_head_up = true;
  sim_punch_requested = false;
  sim_fail = false;
  sim_update_status_flags();
  sim_output_enc();
  sim_output_border();

  sim_next_status_tick_ms = HAL_GetTick();
  __enable_irq();
}

void PunchPressSim_Init(void)
{
  sim_reset(BORDER_ZONE_MM + WORK_AREA_WIDTH_MM / 2.0f, BORDER_ZONE_MM + WORK_AREA_HEIGHT_MM / 2.0f);
}

void PunchPressSim_MainStep()
{
  HAL_GPIO_WritePin(HEARTBEAT_0_GPIO_Port, HEARTBEAT_0_Pin, GPIO_PIN_SET);

  uint32_t now_ms = HAL_GetTick();

  if (!sim_fail) {
    if (!sim_head_up && (int32_t)(now_ms - sim_head_retract_at_ms) > 0) {
      sim_head_up = true;
    }
  }

  while ((int32_t)(now_ms - sim_next_status_tick_ms) > 0)
  {
    sim_next_status_tick_ms += STATUS_PERIOD_MS;
    sim_send_status();
  }

  // uint32_t x_period = HAL_TIM_ReadCapturedValue(&htim2, TIM_CHANNEL_1);
  // uint32_t x_pulse = HAL_TIM_ReadCapturedValue(&htim2, TIM_CHANNEL_2);
  // uint32_t x_counter = __HAL_TIM_GET_COUNTER(&htim2);
  //
  // uint32_t y_period = HAL_TIM_ReadCapturedValue(&htim5, TIM_CHANNEL_2);
  // uint32_t y_pulse = HAL_TIM_ReadCapturedValue(&htim5, TIM_CHANNEL_1);
  // uint32_t y_counter = __HAL_TIM_GET_COUNTER(&htim5);
  //
  // printf("%lu %lu %lu %lu %lu %lu\n", x_period, x_pulse, x_counter, y_period, y_pulse, y_counter);

  int32_t x_enc = (int32_t)((sim_x_pos_mm - BORDER_ZONE_MM) * ENCODER_TICKS_PER_MM);
  int32_t y_enc = (int32_t)((sim_y_pos_mm - BORDER_ZONE_MM) * ENCODER_TICKS_PER_MM);

  if (!sim_fail) {
    if (!sim_head_up) {
      printf(
        "SIM: (%ld, %ld) x=%0.3f y=%0.3f vx=%0.4f vy=%0.4f ix=%0.3f iy=%0.3f fail=%d brd=(%d,%d,%d,%d) pr=%d punching %ld\n",
        x_enc, y_enc,
        sim_x_pos_mm, sim_y_pos_mm, sim_x_speed_mm_per_tick,
        sim_y_speed_mm_per_tick, sim_x_input, sim_y_input,
        sim_fail, sim_border_bottom, sim_border_top, sim_border_left, sim_border_right,
        sim_punch_requested, (int32_t)(sim_head_retract_at_ms - now_ms)
      );
    } else {
      printf(
        "SIM: (%ld, %ld) x=%0.3f y=%0.3f vx=%0.4f vy=%0.4f ix=%0.3f iy=%0.3f fail=%d brd=(%d,%d,%d,%d) pr=%d head up\n",
        x_enc, y_enc,
        sim_x_pos_mm, sim_y_pos_mm, sim_x_speed_mm_per_tick,
        sim_y_speed_mm_per_tick, sim_x_input, sim_y_input,
        sim_fail, sim_border_bottom, sim_border_top, sim_border_left, sim_border_right,
        sim_punch_requested
      );
    }
  }

  HAL_GPIO_WritePin(HEARTBEAT_0_GPIO_Port, HEARTBEAT_0_Pin, GPIO_PIN_RESET);
}

void PunchPressSim_PosStep(void) {
  HAL_GPIO_WritePin(HEARTBEAT_1_GPIO_Port, HEARTBEAT_1_Pin, GPIO_PIN_SET);

  if (sim_fail) {
    HAL_GPIO_TogglePin(HEARTBEAT_1_GPIO_Port, HEARTBEAT_1_Pin);
    return;
  }

  sim_x_input = sim_read_axis_command(&htim2, TIM_CHANNEL_1, TIM_CHANNEL_2);
  sim_y_input = sim_read_axis_command(&htim5, TIM_CHANNEL_2, TIM_CHANNEL_1);

  if (sim_absf(sim_x_speed_mm_per_tick) < STOP_SPEED_MM_PER_TICK && sim_absf(sim_x_input) < INPUT_THRESHOLD) {
    sim_x_speed_mm_per_tick = 0.0f;
  } else {
    float accel = sim_x_input * INPUT_GAIN_MM_PER_TICK2 - sim_x_speed_mm_per_tick * SPEED_DRAG_1_PER_TICK - DYNAMIC_DRAG_MM_PER_TICK2 * sim_signf(sim_x_speed_mm_per_tick);
    sim_x_speed_mm_per_tick += accel;
    sim_x_pos_mm += sim_x_speed_mm_per_tick;
  }

  if (sim_absf(sim_y_speed_mm_per_tick) < STOP_SPEED_MM_PER_TICK && sim_absf(sim_y_input) < INPUT_THRESHOLD) {
    sim_y_speed_mm_per_tick = 0.0f;
  } else {
    float accel = sim_y_input * INPUT_GAIN_MM_PER_TICK2 - sim_y_speed_mm_per_tick * SPEED_DRAG_1_PER_TICK - DYNAMIC_DRAG_MM_PER_TICK2 * sim_signf(sim_y_speed_mm_per_tick);
    sim_y_speed_mm_per_tick += accel;
    sim_y_pos_mm += sim_y_speed_mm_per_tick;
  }

  if (!sim_head_up && (sim_absf(sim_x_speed_mm_per_tick) >= STOP_SPEED_MM_PER_TICK || sim_absf(sim_y_speed_mm_per_tick) >= STOP_SPEED_MM_PER_TICK)) {
    sim_fail = true;
  }

  sim_update_status_flags();
  sim_output_border();
  sim_output_enc();

  HAL_GPIO_WritePin(HEARTBEAT_1_GPIO_Port, HEARTBEAT_1_Pin, GPIO_PIN_RESET);
}

void PunchPressSim_ProcessRestartPacket(const SimulationRestart *packet) {
  sim_reset((float)packet->x_100um / 100.0f, (float)packet->y_100um / 100.0f);
}

void PunchPressSim_ProcessPunchRequest(bool punch_requested) {
  if (punch_requested != sim_punch_requested) {
    if (punch_requested) {
      sim_head_up = false;
      sim_head_retract_at_ms = HAL_GetTick() + HEAD_RETRACT_TIME_MS;
      printf("PUNCH\n");
      sim_send_punch();
    }
  }
  sim_punch_requested = punch_requested;
}
