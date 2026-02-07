# 故障定义：GPS 天线开路/短路 (GPS Antenna Open/Short Circuit)

## 1. 故障描述
基站 GNSS 接收模块通过馈线连接外部 GPS 天线，对天线供电并接收卫星信号。  
当天线连接异常（开路或短路）时，GNSS 模块无法搜星，导致 GNSS 参考源不可用。  
若无备用参考源（1588v2/SyncE），系统将进入 Holdover 模式，最终可能进入自由振荡状态。

## 2. 涉及模块
| 模块 | 说明 |
|------|------|
| **GNSS_RCV** | GNSS 接收机模块，负责天线检测和搜星 |
| **CLK_REF_SEL** | 时钟参考源选择与切换 |
| **HOLDOVER_CTRL** | Holdover 保持控制 |
| **RF_CTRL** | 射频定时（受间接影响） |

## 3. 日志特征 (判据)

### 必要条件
1. **天线电压异常**: `antenna voltage abnormal` + 电压 ∉ [4.6V, 5.4V]
2. **天线故障检测**: `antenna connection fault detected: SHORT_CIRCUIT` 或 `OPEN_CIRCUIT`

### 伴随特征
3. `Satellite tracking lost, visible_SVs=0` — 所有卫星跟踪丢失
4. `GNSS reference source unavailable` — GNSS 参考源不可用
5. `Holdover mode activated` — 系统进入保持模式
6. 长时间后可能出现 `Holdover.*exceeded threshold` — 保持超时

### 电压判断标准
| 测量电压 | 判定 |
|---------|------|
| 0V～1V | 短路 (SHORT_CIRCUIT) |
| 1V～4.5V | 馈线阻抗异常 |
| 4.6V～5.4V | 正常 |
| >5.5V | 开路 (OPEN_CIRCUIT) |

## 4. 排查步骤
1. **检查避雷器**（最常见故障原因）：
   - 雷击导致避雷器损坏（开路/短路）
   - 避雷器锈蚀或连接松动
   - 避雷器防水不完善导致进水
2. **检查 GPS 信号线缆**：
   - GPS 接口到主控板 ANT 接口的连接是否牢固
   - 馈线有无弯折、断裂、进水
3. **检查 GPS 天线本体**：
   - 天线是否物理损坏
   - 天线安装位置是否有遮挡（需要上空视角 >90°）
4. **检查备用参考源配置**：
   - 是否配置了 1588v2 备用源（减少对 GPS 单一依赖）
   - SyncE 是否已启用

## 5. 典型故障时序
```
t0: GPS 天线电压异常 (0.2V，短路)       ← 硬件故障
t1: 天线故障检测：SHORT_CIRCUIT
t2: 卫星跟踪全部丢失 (SVs=0)
t3: GNSS 参考源不可用 → 尝试切换备用源
t4: 备用源不可用 → 进入 Holdover
t5: Holdover 超时 → RF 帧偏移超限       ← 业务中断
```
