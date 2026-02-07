# 故障定义：Holdover 超时 / 进入自由振荡 (Holdover Timeout / Free-Running)

## 1. 故障描述
当基站所有外部参考源（GNSS、1588v2、SyncE）全部不可用时，系统进入 Holdover 模式，  
依赖本地高精度晶振（OCXO）维持时钟精度。但晶振有固有漂移，精度会随时间持续劣化。  

关键指标：
- **OCXO**: 典型漂移 ~1μs/小时，最大保持 ~24 小时
- **TCXO**: 典型漂移 ~10μs/小时，最大保持 ~数分钟

当 Holdover 超时（超过晶振可保证精度的最大时间），系统进入 **FREE_RUN（自由振荡）** 模式。  
此时时钟精度不可控，基站被视为"时间孤岛"，**必须现场处理**。

## 2. 涉及模块
| 模块 | 说明 |
|------|------|
| **HOLDOVER_CTRL** | Holdover 保持控制与超时监控 |
| **CLK_CORE** | 时钟状态机（HOLDOVER → FREE_RUN 跳转） |
| **CLK_REF_SEL** | 参考源选择（所有源不可用） |
| **RF_CTRL** | 射频定时（帧偏移超限） |

## 3. 日志特征 (判据)

### Holdover 阶段（WARN 级别）
1. **进入 Holdover**: `Holdover mode activated` + 晶振类型 + 预估漂移率
2. **Holdover 监控**: `Holdover elapsed=XXXs` + `phase_offset` + `drift_rate` + `quality`

### 超时/FREE_RUN 阶段（FATAL 级别）
3. **Holdover 超时**: `Holdover maximum duration exceeded`
4. **进入自由振荡**: `Clock state transition: HOLDOVER -> FREE_RUN`
5. **时钟质量未知**: `System clock quality degradation to UNKNOWN`

### Holdover 质量等级
| quality 值 | 含义 | 典型偏移 |
|-----------|------|---------|
| GOOD | 精度可接受 | <1.5μs |
| ACCEPTABLE | 精度开始劣化 | 1.5μs~10μs |
| DEGRADED | 精度明显劣化 | 10μs~50μs |
| UNKNOWN | 不可控（FREE_RUN） | >50μs 或无法评估 |

## 4. 排查步骤
1. **确认进入 Holdover 的根因**：
   - 是 GNSS 故障（天线/信号）还是 PTP 故障（链路/Master）？
   - 是单源故障还是全源故障？
2. **恢复任一外部参考源（紧急措施）**：
   - 最快方式：修复 GPS 天线连接
   - 备选：配置临时的 1588v2 链路
3. **评估 Holdover 已经持续的时间**：
   - 如已超过 1 小时（OCXO），业务已中断
   - 如已超过 24 小时，系统可能已在 FREE_RUN
4. **现场检查硬件**：
   - GPS 天线及馈线
   - 传输光纤/网线
   - 避雷器
   - 主控板状态灯
5. **恢复后确认**：
   - PLL 是否重新锁定（LOCKED, state_reg=0x0）
   - 帧偏移是否回到正常范围（<±1.5μs）
   - RF TX 是否恢复

## 5. 典型故障时序（完整 24 小时）
```
t+0h:    GPS 天线故障 → 1588v2 不可用 → 进入 Holdover
t+0h:    Holdover 启动，OCXO 开始漂移
t+1h:    相位偏移 ~1μs (quality=GOOD)
t+1h12m: 帧偏移超限 (>1.5μs)，TX 关闭      ← 业务中断
t+4h:    相位偏移 ~4μs (quality=ACCEPTABLE)
t+10h:   相位偏移 ~11μs (quality=DEGRADED)
t+24h:   Holdover 超时，进入 FREE_RUN        ← 严重告警
         需要现场处理
```
