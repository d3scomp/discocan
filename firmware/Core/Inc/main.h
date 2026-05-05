/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.h
  * @brief          : Header for main.c file.
  *                   This file contains the common defines of the application.
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

/* Define to prevent recursive inclusion -------------------------------------*/
#ifndef __MAIN_H
#define __MAIN_H

#ifdef __cplusplus
extern "C" {
#endif

/* Includes ------------------------------------------------------------------*/
#include "stm32f4xx_hal.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */

/* USER CODE END Includes */

/* Exported types ------------------------------------------------------------*/
/* USER CODE BEGIN ET */

/* USER CODE END ET */

/* Exported constants --------------------------------------------------------*/
/* USER CODE BEGIN EC */

/* USER CODE END EC */

/* Exported macro ------------------------------------------------------------*/
/* USER CODE BEGIN EM */

/* USER CODE END EM */

/* Exported functions prototypes ---------------------------------------------*/
void Error_Handler(void);

/* USER CODE BEGIN EFP */

/* USER CODE END EFP */

/* Private defines -----------------------------------------------------------*/
#define PC14_OSC32_IN_Pin GPIO_PIN_14
#define PC14_OSC32_IN_GPIO_Port GPIOC
#define PC15_OSC32_OUT_Pin GPIO_PIN_15
#define PC15_OSC32_OUT_GPIO_Port GPIOC
#define PH0_OSC_IN_Pin GPIO_PIN_0
#define PH0_OSC_IN_GPIO_Port GPIOH
#define PH1_OSC_OUT_Pin GPIO_PIN_1
#define PH1_OSC_OUT_GPIO_Port GPIOH
#define HEARTBEAT_3_Pin GPIO_PIN_1
#define HEARTBEAT_3_GPIO_Port GPIOC
#define HEARTBEAT_2_Pin GPIO_PIN_2
#define HEARTBEAT_2_GPIO_Port GPIOC
#define PWM_Y_Pin GPIO_PIN_1
#define PWM_Y_GPIO_Port GPIOA
#define BOOT1_Pin GPIO_PIN_2
#define BOOT1_GPIO_Port GPIOB
#define HEARTBEAT_1_Pin GPIO_PIN_9
#define HEARTBEAT_1_GPIO_Port GPIOE
#define BORDER_RIGHT_Pin GPIO_PIN_11
#define BORDER_RIGHT_GPIO_Port GPIOE
#define HEARTBEAT_0_Pin GPIO_PIN_12
#define HEARTBEAT_0_GPIO_Port GPIOE
#define BORDER_LEFT_Pin GPIO_PIN_13
#define BORDER_LEFT_GPIO_Port GPIOE
#define SWDIO_Pin GPIO_PIN_13
#define SWDIO_GPIO_Port GPIOA
#define SWCLK_Pin GPIO_PIN_14
#define SWCLK_GPIO_Port GPIOA
#define PWM_X_Pin GPIO_PIN_15
#define PWM_X_GPIO_Port GPIOA
#define ENC_Y_A_Pin GPIO_PIN_12
#define ENC_Y_A_GPIO_Port GPIOC
#define ENC_Y_B_Pin GPIO_PIN_0
#define ENC_Y_B_GPIO_Port GPIOD
#define CAN1_STB_Pin GPIO_PIN_3
#define CAN1_STB_GPIO_Port GPIOD
#define OTG_FS_OverCurrent_Pin GPIO_PIN_5
#define OTG_FS_OverCurrent_GPIO_Port GPIOD
#define ENC_X_B_Pin GPIO_PIN_7
#define ENC_X_B_GPIO_Port GPIOD
#define SWO_Pin GPIO_PIN_3
#define SWO_GPIO_Port GPIOB
#define BORDER_TOP_Pin GPIO_PIN_4
#define BORDER_TOP_GPIO_Port GPIOB
#define ENC_X_A_Pin GPIO_PIN_5
#define ENC_X_A_GPIO_Port GPIOB
#define BORDER_BOTTOM_Pin GPIO_PIN_7
#define BORDER_BOTTOM_GPIO_Port GPIOB

/* USER CODE BEGIN Private defines */

/* USER CODE END Private defines */

#ifdef __cplusplus
}
#endif

#endif /* __MAIN_H */
