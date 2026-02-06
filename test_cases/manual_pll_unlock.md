# 故障定义：系统主时钟 PLL 失锁 (System PLL Unlock)

## 1. 故障描述
基站主控板的时钟子系统（CLK）依赖锁相环（PLL）锁定外部参考源（如 GPS 或 1588）。
当 PLL 状态从“锁定（LOCK）”变为“失锁（UNLOCK）”时，会导致基站空口定时异常，业务中断。

## 2. 涉及模块
* **ModuleID**: CLK (Clock Subsystem)
* **Sub-Module**: PLL_CTRL

## 3. 日志特征 (判据)
在日志中检索到以下关键打印之一，即可判定为 PLL 失锁：
1.  **关键报错 1**: `PLL status changed: LOCK -> UNLOCK`
2.  **关键报错 2**: `Fatal Error: System PLL lost lock, current_state=0x3`
3.  **伴随报错**: `[BSP] Sync request failed due to clock unstable`

**注意**：`current_state=0x3` 是硬件寄存器返回的特定失锁状态码。

## 4. 排查步骤
1.  检查 GPS 天线连接是否松动。
2.  检查是否强制配置了不可用的参考源（如强制切到 1588 但网线未插）。
3.  如果是偶发失锁，可能是板卡硬件老化，建议更换主控板。