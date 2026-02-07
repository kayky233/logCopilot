# 故障定义：时钟源切换振荡 (Clock Source Oscillation)

## 1. 故障描述
基站时钟子系统配置了多个参考源（如 GNSS + 1588v2），当高优先级参考源质量不稳定（反复劣化-恢复）时，  
系统会在两个参考源之间频繁切换。每次切换 PLL 需要重新锁定（ACQUIRING），期间输出时钟精度下降。  
频繁切换（振荡）比单次切换危害更大：PLL 持续处于捕获状态，无法稳定锁定，可能导致隐性的帧偏移累积。

系统内置振荡检测机制：若 **120秒内切换次数 ≥ 3次**，则触发切换抑制（Switchover Suppression），锁定当前源。

## 2. 涉及模块
| 模块 | 说明 |
|------|------|
| **CLK_REF_SEL** | 参考源选择与切换控制 |
| **PLL_CTRL** | PLL 状态（反复 ACQUIRING → LOCKED） |
| **GNSS_RCV** | GNSS 信号（不稳定的源头） |
| **PTP_CLIENT** | 1588v2（被动角色，备用源） |

## 3. 日志特征 (判据)

### 必要条件
1. **振荡检测**: `Clock source oscillation detected` + `switchover_count` 超过阈值
2. **切换抑制**: `Suppressing switchover, locking current source`

### 伴随特征
3. 密集的 `Ref source switchover` 日志（短时间内多次）
4. SSM 质量频繁跳变：`PRC → DNU → PRC → DNU`
5. PLL 频繁在 ACQUIRING / LOCKED 间切换

## 4. 排查步骤
1. **确认不稳定的参考源**：
   - 从日志中确认是哪个参考源在反复劣化（通常是 GNSS）
   - 检查该参考源的信号质量（卫星 SNR、天线状态、PTP PDV 等）
2. **排查电磁干扰**：
   - 间歇性的 GNSS 信号波动常因附近有间歇性干扰源（如塔顶设备间歇工作的微波天线）
3. **调整反切迟滞参数**：
   - 增大 WTR (Wait To Restore) 时间，让恢复的参考源保持稳定更久才切回
   - 典型建议：WTR ≥ 300秒
4. **考虑锁定备用源**：
   - 如果 GNSS 持续不稳定，可手动锁定 1588v2 为主用源
   - 或者临时降低 GNSS 优先级

## 5. 典型故障时序
```
t0: GNSS 信号不稳定 (SNR 波动)
t1: GNSS SSM 降级 → 切换到 1588v2           ← 第1次切换
t2: PLL ACQUIRING → LOCKED (1588v2)
t3: GNSS 恢复 → 切回 GNSS                   ← 第2次切换
t4: GNSS 又劣化 → 切到 1588v2               ← 第3次切换
t5: GNSS 又恢复 → 切回 GNSS                 ← 第4次切换
t6: 振荡检测触发 (5次/75s > 3次/120s阈值)
t7: 切换抑制，锁定当前源                     ← 保护机制生效
```
