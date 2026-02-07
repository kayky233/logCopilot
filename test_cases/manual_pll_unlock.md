# 故障定义：系统主时钟 PLL 失锁 (System PLL Unlock)

## 1. 故障描述
基站主控板（BBU/UMPT）的时钟子系统（CLK）依赖数字锁相环（DPLL/PLL）锁定外部参考源（如 GNSS 或 1588v2）。
当 PLL 状态从 **LOCKED** 跳变为 **UNLOCK** 时，系统时钟失去基准，导致：
- RF 空口帧定时偏移超限（>±1.5μs），基站发射机被关闭
- 基带处理无法维持同步，业务全部中断
- 系统触发软件复位尝试恢复

## 2. 涉及模块
| 模块 | 说明 |
|------|------|
| **CLK_CORE** | 时钟子系统核心控制 |
| **PLL_CTRL** | 锁相环状态监控 |
| **CLK_REF_SEL** | 参考源选择 |
| **BSP_SYNC** | BSP 同步请求接口 |
| **RF_CTRL** | 射频定时控制 |

## 3. 日志特征 (判据)
在板级日志（pltf.SwLogs / run_log）中检索到以下关键打印，即可判定为 PLL 失锁：

### 必要条件（任一命中即判定）
1. **关键报错**: `PLL status changed: LOCK -> UNLOCK` — PLL 状态跳变
2. **严重报错**: `Fatal Error: System PLL lost lock, current_state=0x3` — 硬件寄存器 0x3 = Reference Lost

### 伴随报错（辅助确认）
3. `reference jitter exceed threshold` — 失锁前的先兆：抖动超限
4. `Sync request failed due to clock unstable` — BSP 层同步请求失败
5. `Radio frame timing offset` + 偏移量 > 1.5μs — RF 层影响确认

### 状态码说明
| state_reg 值 | 含义 |
|-------------|------|
| 0x0 | PLL 正常锁定 |
| 0x1 | PLL 捕获中 (ACQUIRING) |
| 0x2 | PLL 保持模式 (HOLDOVER) |
| **0x3** | **参考源丢失，严重失锁 (Reference Lost)** |

## 4. 排查步骤
1. **检查参考源状态**：
   - 查看 GNSS 模块是否正常：卫星数量 ≥4、SNR ≥15。
   - 查看 1588v2 PTP 链路是否正常：Announce 消息是否超时。
2. **检查 GPS 天线**：
   - 天线馈线连接是否松动或损坏。
   - 天线电压是否在 4.6V～5.4V 范围内（排除开路/短路）。
   - 避雷器状态是否正常。
3. **检查时钟源切换记录**：
   - 是否存在频繁的时钟源切换（切换振荡），导致 PLL 无法稳定锁定。
   - 是否强制配置了不可用的参考源。
4. **检查环境因素**：
   - 雷击是否损坏避雷器或GPS天线。
   - 机房温度是否异常导致晶振频偏。
5. **硬件排查**：
   - 如果是偶发失锁且排除外部因素，可能是主控板 DPLL 芯片老化，建议更换主控板。
   - 检查板卡上 OCXO/TCXO 晶振是否老化（可通过 Holdover 精度劣化速度判断）。

## 5. 典型故障时序
```
t0: GNSS 信号开始劣化 (SNR 下降)
t1: PLL 抖动超过阈值 (>50ns)       ← 先兆告警
t2: PLL LOCK → UNLOCK (state=0x3)  ← 故障发生
t3: BSP 同步请求失败
t4: RF 帧偏移超限，TX 关闭          ← 业务中断
t5: 系统触发软件复位
```
