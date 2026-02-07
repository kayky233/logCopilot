# 故障定义：GNSS 搜星不足 (GNSS Insufficient Satellites)

## 1. 故障描述
基站 GNSS 接收模块搜索到的可见卫星数量不足 4 颗，无法完成三维定位和授时。  
GNSS 1PPS 信号无效，时钟子系统无法锁定 GNSS 参考源，系统只能依赖 Holdover 或其他备用参考源。  
长时间搜星不足会导致 Holdover 超时，最终帧偏移超限影响业务。

## 2. 涉及模块
| 模块 | 说明 |
|------|------|
| **GNSS_RCV** | GNSS 接收机模块 |
| **PLL_CTRL** | PLL 状态（无法锁定 GNSS 参考） |
| **HOLDOVER_CTRL** | Holdover 保持控制 |
| **RF_CTRL** | 射频定时（受间接影响） |

## 3. 日志特征 (判据)

### 必要条件
1. **搜星不足**: `Insufficient satellites` 且 visible < 4
2. **搜星超时**: `Search timeout` + 卫星数仍不足

### 伴随特征
3. `GNSS time source not ready` + `1PPS signal invalid` — 授时信号无效
4. `SNR below threshold` — 可见卫星信噪比低
5. `PLL unable to lock to GNSS reference` — PLL 无法锁定

## 4. 排查步骤
1. **确认是否初次上电**：初次上电搜星需要 10 分钟以上（冷启动），等待即可。
2. **检查天线安装位置**：
   - 上空视角需 >90°（竖直向上视野开阔）
   - 周围不能有高大建筑物遮挡
3. **排查电磁干扰**：
   - 检查附近是否有大功率微波天线、高压输电线等干扰源
   - 使用频谱仪检测 GPS L1 频段 (1.57542GHz±20MHz) 是否有干扰
4. **检查星卡位置信息**：
   - 星卡/GNSS 模块中配置的经纬度是否与实际位置偏差过大
   - 星卡模式（单/双模）是否与实际配置一致
5. **检查天线馈线链路**：
   - 馈线接头是否松动、进水
   - 如使用功分器（多 BBU 共用天线），检查功分器状态

## 5. 典型故障时序
```
t0: GNSS 搜星启动
t1: 搜到卫星数不足 (2/4)
t2: 搜星超时 (60s)，仍不足
t3: GNSS 1PPS 信号无效
t4: PLL 无法锁定 → 保持 Holdover
t5: Holdover 精度劣化，相位偏移持续增大
t6: 相位偏移超限 (>1.5μs)         ← 业务受影响
```
