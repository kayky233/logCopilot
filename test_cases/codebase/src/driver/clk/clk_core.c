/* * File: src/driver/clk/clk_core.c
 * Module: Clock Driver
 */

 #include "clk_hal.h"

 // 检查 PLL 状态的守护任务
 void Clk_CheckPllStatus(void) {
     int state = HAL_ReadPllRegister();
     
     // 如果之前是锁定状态，现在读出来的不是锁定
     if (g_last_status == PLL_LOCKED && state != PLL_LOCKED) {
         
         // 打印状态变更日志
         LOG_ERROR("[CLK] PLL status changed: LOCK -> UNLOCK");
         
         // 0x3 代表严重的失锁状态 (Reference Lost)
         if (state == 0x3) {
             // Line 405: 这里的报错是我们在日志里看到的
             LOG_FATAL("Fatal Error: System PLL lost lock, current_state=0x3");
             
             // 触发系统紧急停机
             BSP_SystemHalt();
         }
     }
     
     g_last_status = state;
 }