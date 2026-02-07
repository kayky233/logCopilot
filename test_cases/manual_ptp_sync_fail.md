# 故障定义：1588v2 PTP 同步失败 (PTP Synchronization Failure)

## 1. 故障描述
基站通过 IEEE 1588v2 精密时间协议 (PTP) 从地面网络获取时间/频率参考。  
当 PTP Master 不可达（Announce 消息超时）或 PTP 时间锁定失败时，1588v2 参考源变为不可用。  
若站点未配置 GNSS 备用源（常见于纯室分/隧道场景），系统将直接进入 Holdover 模式。

## 2. 涉及模块
| 模块 | 说明 |
|------|------|
| **PTP_CLIENT** | PTP 从时钟客户端 (Slave) |
| **CLK_REF_SEL** | 时钟参考源选择与切换 |
| **HOLDOVER_CTRL** | Holdover 保持控制 |
| **GNSS_RCV** | GNSS（如未配置则不可回退） |

## 3. 日志特征 (判据)

### 必要条件
1. **Announce 超时**: `PTP Announce message timeout` — Master 消息中断
2. **Master 不可达**: `PTP Master unreachable` + BMCA 状态 SLAVE → LISTENING
3. **时间失锁**: `PTP time lock failed` + `hwPtpTimeLockFailReason`

### 伴随特征
4. `path delay variation increased` — 失败前的先兆：PDV 增大
5. `1588v2 reference source unavailable` — 参考源不可用
6. `All external references lost` — 无备用参考源可用

### PTP 时间失锁原因码
| hwPtpTimeLockFailReason | 含义 |
|------------------------|------|
| masterLost | PTP Master 不可达 |
| frequencyUnLock | 频率锁定失败 |
| phaseUnLock | 相位锁定失败 |
| portPtsf | 端口 PTSF (Packet Timing Signal Fail) |

## 4. 排查步骤
1. **检查传输链路**：
   - 基站到汇聚交换机之间的光纤/网线是否正常
   - 交换机端口是否 Down 或有大量丢包/CRC 错误
   - 是否发生了网络设备升级/割接导致的临时中断
2. **检查上游 PTP 设备**：
   - 上游 T-BC (电信边界时钟) 是否正常工作
   - PTP Grandmaster 是否故障
   - PTP Domain 配置是否一致
3. **检查 PTP 配置**：
   - PTP Profile (G.8275.1/G.8275.2) 与网络侧是否匹配
   - 延时机制 (E2E/P2P) 是否一致
   - VLAN 配置是否正确
4. **检查 PDV (时延抖动)**：
   - 链路上是否有非 PTP-Aware 的设备（引入大量 PDV）
   - 是否有大量突发流量影响 PTP 报文传输

## 5. 典型故障时序
```
t0: PTP 路径延时抖动增大 (PDV 异常)     ← 先兆
t1: PTP Announce 超时 (3×Announce间隔)
t2: PTP Master 不可达，BMCA → LISTENING
t3: PTP 时间失锁 (hwPtpTimeLockFail)
t4: 1588v2 参考源不可用
t5: GNSS 不可用 → 全部参考源丢失
t6: 进入 Holdover 模式                  ← 业务倒计时开始
```
