# TNPC 梯形波生成原理分析

## 概述

本文档分析如何使用 F28379D 的 EPWM 模块生成 TNPC 逆变器所需的梯形波控制信号。

**目标波形：** 0电平 → 高电平 → 0电平 → 低电平（周期循环）

**对应电压：** 0V → +Udc/2 → 0V → -Udc/2

---

## 核心参数

```c
#define CARRIER     1000    // TBPRD，载波周期
#define CMP_L       295     // 比较值A，29.5%
#define CMP_H       705     // 比较值B，70.5%
#define DEADTIME    10      // 死区时间，100ns
```

**频率计算：**
- EPWMCLK = 100MHz
- PWM 频率 = 100MHz / (2 × 1000) = **50kHz**
- 周期 = 20μs

---

## Up-Down 计数模式

### 计数器行为

```
计数器 TBCTR：0 → 1000 → 0 → 1000 → 0 ...
              ↑上升↑  ↓下降↓  ↑上升↑
```

**关键时刻：**
- **ZRO**：计数器 = 0
- **CAU**：计数器上升到 CMPA (295)
- **CAD**：计数器下降到 CMPA (295)
- **CBU**：计数器上升到 CMPB (705)
- **CBD**：计数器下降到 CMPB (705)
- **PRD**：计数器 = TBPRD (1000)

---

## 三路信号生成逻辑

### 信号映射

| GPIO | EPWM | 功能 | 对应开关 | 输出电压 |
|------|------|------|---------|---------|
| GPIO11 | EPWM6B | GA | S1 上桥臂 | +Udc/2 |
| GPIO0/2 | EPWM1A/2A | G0 | S2/S4 中点钳位 | 0V |
| GPIO6 | EPWM4A | GB | S3 下桥臂 | -Udc/2 |

### 时序关系

```
时间轴:     0   2.95μs 5.9μs  14.1μs 14.15μs 20μs
            |     |      |       |       |      |
计数器:     0    295    705    1000    705    295    0
            ↑     ↑      ↑       ↑       ↑      ↑     ↑
           ZRO   CAU    CBU     PRD     CBD    CAD   ZRO

GA(GPIO11): ‾‾‾‾‾‾|______|______|______|______|‾‾‾‾‾‾
            高29.5%|           低70.5%          |高29.5%

G0(GPIO0):  ______|‾‾‾‾‾‾‾‾‾‾‾‾|______|‾‾‾‾‾‾‾‾‾‾‾‾
                   |    高41%   |      |    高41%

GB(GPIO6):  ______|______|‾‾‾‾‾‾|______|______|______
                          |高29.5%|

输出电压:   +Udc/2  0V   -Udc/2  -Udc/2  0V   +Udc/2
```

---

## 详细实现机制

### 1. EPWM6B (GA) - 上桥臂 S1

**目标：** 在计数器 < 295 时输出高电平

**Action Qualifier 配置：**
```c
EPwm6Regs.AQCTLB.bit.ZRO = AQ_SET;     // 计数器=0 → 输出高
EPwm6Regs.AQCTLB.bit.CAU = AQ_CLEAR;   // 上升到295 → 输出低
EPwm6Regs.AQCTLB.bit.CAD = AQ_SET;     // 下降到295 → 输出高
```

**时序：**
- 上升阶段：0 → 295，输出高（29.5%）
- 上升阶段：295 → 1000，输出低
- 下降阶段：1000 → 295，输出低
- 下降阶段：295 → 0，输出高（29.5%）

**占空比：** 29.5% × 2 = 59%（但只在谷底附近高）

### 2. EPWM1A/2A (G0) - 中点钳位 S2/S4

**目标：** 在计数器 295~705 之间输出高电平

**Action Qualifier 配置：**
```c
EPwm1Regs.AQCTLA.bit.ZRO = AQ_CLEAR;   // 计数器=0 → 输出低
EPwm1Regs.AQCTLA.bit.CAU = AQ_SET;     // 上升到295 → 输出高
EPwm1Regs.AQCTLA.bit.CBU = AQ_CLEAR;   // 上升到705 → 输出低
EPwm1Regs.AQCTLA.bit.CAD = AQ_CLEAR;   // 下降到295 → 输出低
EPwm1Regs.AQCTLA.bit.CBD = AQ_SET;     // 下降到705 → 输出高
```

**时序：**
- 上升阶段：0 → 295，输出低
- 上升阶段：295 → 705，输出高（41%）
- 上升阶段：705 → 1000，输出低
- 下降阶段：1000 → 705，输出低
- 下降阶段：705 → 295，输出高（41%）
- 下降阶段：295 → 0，输出低

**占空比：** 41% × 2 = 82%（在中间区域高）

### 3. EPWM4A (GB) - 下桥臂 S3

**目标：** 在计数器 > 705 时输出高电平

**Action Qualifier 配置：**
```c
EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;   // 计数器=0 → 输出低
EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;     // 上升到705 → 输出高
EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;   // 下降到705 → 输出低
```

**时序：**
- 上升阶段：0 → 705，输出低
- 上升阶段：705 → 1000，输出高（29.5%）
- 下降阶段：1000 → 705，输出高（29.5%）
- 下降阶段：705 → 0，输出低

**占空比：** 29.5% × 2 = 59%（但只在峰顶附近高）

---

## 互补关系验证

### 任意时刻只有一路为高

| 计数器范围 | GA | G0 | GB | 输出电压 |
|-----------|----|----|----|---------| 
| 0 ~ 295 (上升) | 高 | 低 | 低 | +Udc/2 |
| 295 ~ 705 (上升) | 低 | 高 | 低 | 0V |
| 705 ~ 1000 (上升) | 低 | 低 | 高 | -Udc/2 |
| 1000 ~ 705 (下降) | 低 | 低 | 高 | -Udc/2 |
| 705 ~ 295 (下降) | 低 | 高 | 低 | 0V |
| 295 ~ 0 (下降) | 高 | 低 | 低 | +Udc/2 |

**安全性：** ✓ 任意时刻只有一路为高，满足 TNPC 安全约束

---

## 死区实现方式

### 方式一：通过比较值间隔实现（推荐）

**原理：** 调整 CMP_L 和 CMP_H 的值，在切换点之间留出间隙

**配置示例：**
```c
#define CARRIER     1000
#define CMP_L       295     // 29.5%
#define CMP_H       705     // 70.5%
// 死区间隔：295~300 和 700~705 = 5 TBCLK = 50ns

// 禁用硬件死区模块
EPwm1Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
EPwm2Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
EPwm4Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
EPwm6Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
```

**波形效果：**
```
0~295:   GA高
295~300: 三路都低 ← 死区 50ns
300~705: G0高
705~710: 三路都低 ← 死区 50ns
710~1000: GB高
```

**优势：**
- 真正的"三路都关断"死区
- 配置简单，时序清晰
- 占空比精确可控
- 适合 TNPC 三路互斥信号

**代码参考：** tixing3.c

---

### 方式二：使用硬件死区模块（DB_ACTV_HIC 互补模式）

**原理：** 利用死区模块的互补输出特性，在切换时自动插入死区

**死区模块工作机制：**

死区模块内部生成两个信号：
- **RED (Rising Edge Delayed)**: 上升沿延迟 DBRED 的信号
- **FED (Falling Edge Delayed)**: 下降沿延迟 DBFED 的信号

**DB_ACTV_HIC 模式下的输出分配：**
- **EPWMxA = RED**
- **EPWMxB = ~FED** (FED 的反相)

**死区效果：**

1. **当 AQ 输出从低→高时：**
   - EPWMxA (RED)：延迟 DBRED 后上升
   - EPWMxB (~FED)：立即下降
   - 死区：DBRED 期间两路都低

2. **当 AQ 输出从高→低时：**
   - EPWMxA (RED)：立即下降
   - EPWMxB (~FED)：延迟 DBFED 后上升
   - 死区：DBFED 期间两路都低

**关键理解：**
- **DBRED 控制 EPWMxA 的上升沿延迟**
- **DBFED 控制 EPWMxB 的上升沿延迟**

**配置示例：**
```c
#define CARRIER     1000
#define CMP_L       200     // 20%
#define CMP_H       600     // 60%
#define DEADTIME    10      // 100ns

// EPWM1/2/4 配置 EPWMxA 输出
EPwm1Regs.DBRED = DEADTIME;
EPwm1Regs.DBFED = DEADTIME;
EPwm1Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
EPwm1Regs.DBCTL.bit.IN_MODE = DBA_ALL;
EPwm1Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

// EPWM6 配置 EPWMxB 输出（互补）
EPwm6Regs.AQCTLA.bit.CAU = AQ_SET;    // 配置 A 通道
EPwm6Regs.AQCTLA.bit.CAD = AQ_CLEAR;
EPwm6Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
EPwm6Regs.AQCTLA.bit.PRD = AQ_SET;
EPwm6Regs.DBRED = DEADTIME;
EPwm6Regs.DBFED = DEADTIME;
EPwm6Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
EPwm6Regs.DBCTL.bit.IN_MODE = DBA_ALL;
EPwm6Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;
```

**时序分析（以 EPWM6 为例）：**

AQ 输出在 200~1000 之间为高：

- **上升阶段：**
  - 0~200: EPWM6B 高（GA 高）
  - 200~210: 死区（DBRED=10）
  - 210~1000: EPWM6B 低（GA 低）

- **下降阶段：**
  - 1000~200: EPWM6B 低（GA 低）
  - 200~210: 死区（DBFED=10）
  - 210~0: EPWM6B 高（GA 高）

**完整三路时序：**
```
计数器:  0   200 210   600 610   1000  610 600   210 200   0

上升阶段:
GA:      ‾‾‾‾‾‾‾‾‾|_________________________________
         (0~200)  ↑死区↑
G0:      _________|‾‾‾‾‾‾‾‾‾‾|_____________________
         (210~600)          ↑死区↑
GB:      _____________________|‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾
         (610~1000)

下降阶段:
GB:      ‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾‾|_____________________
         (1000~600)         ↑死区↑
G0:      _____________________|‾‾‾‾‾‾‾‾‾‾|_________
         (610~200)                    ↑死区↑
GA:      _________________________________|‾‾‾‾‾‾‾‾
         (210~0)
```

**优势：**
- 所有切换点都有死区保护
- 上升和下降阶段对称
- 硬件自动实现，无需手动调整比较值

**注意事项：**
- 需要正确理解 DB_ACTV_HIC 模式的互补输出机制
- EPWM6 需要配置 AQCTLA（A 通道），输出使用 EPWM6B（B 通道）
- DBRED 和 DBFED 都需要设置，分别控制两个方向的死区

**代码参考：** tixing11.c

---

## 占空比计算

### 一个完整周期（0→1000→0）

**方式一（比较值间隔死区）：**
- GA 高：0~295 (上升) + 295~0 (下降) = **29.5% × 2 = 59%**
- G0 高：300~705 (上升) + 705~300 (下降) = **40.5% × 2 = 81%**
- GB 高：710~1000 (上升) + 1000~710 (下降) = **29% × 2 = 58%**
- 死区：(5+5) × 2 = **2%**

**方式二（硬件死区模块）：**
- GA 高：(200 + 190) / 2000 = **19.5%**
- G0 高：(390 + 390) / 2000 = **39%**
- GB 高：(390 + 400) / 2000 = **39.5%**
- 死区：4 个切换点 × 10 TBCLK = **2%**

---

## 修改占空比的方法

### 调整 CMP_L 和 CMP_H

**公式：**
```c
duty_P = CMP_L / CARRIER          // 正电压占空比
duty_0 = (CMP_H - CMP_L) / CARRIER  // 零电压占空比
duty_N = (CARRIER - CMP_H) / CARRIER  // 负电压占空比
```

**示例：** 要实现 30% / 40% / 30%
```c
#define CMP_L  300  // 30%
#define CMP_H  700  // 70% → 30% 负电压
// duty_0 = (700-300)/1000 = 40%
```

---

## 同步机制

### Master-Slave 架构

```c
// EPWM1 = Master
EPwm1Regs.TBCTL.bit.PHSEN = TB_DISABLE;
EPwm1Regs.TBCTL.bit.SYNCOSEL = TB_CTR_ZERO;

// EPWM2/4/6 = Slave
EPwm2Regs.TBCTL.bit.PHSEN = TB_ENABLE;
EPwm2Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;
```

**同步触发：**
```c
EPwm1Regs.TBCTL.bit.SWFSYNC = 1;  // 软件强制同步
```

**效果：** 所有 EPWM 模块的计数器同步，确保三路信号时序一致

---

## 配置方案对比

| 特性 | 方式一：比较值间隔 | 方式二：硬件死区模块 |
|------|------------------|-------------------|
| 死区实现 | 调整 CMP_L/CMP_H | DBRED/DBFED |
| 配置复杂度 | 简单 | 中等 |
| 死区对称性 | 完全对称 | 完全对称 |
| 占空比精度 | 高 | 高 |
| 适用场景 | 通用 | 需要互补输出 |
| 代码参考 | tixing3.c | tixing11.c |

---

## 关键优势

1. **硬件自动生成**：无需 ISR，全部由 EPWM 硬件完成
2. **精确时序**：Up-Down 模式天然对称
3. **安全互补**：AQ 配置保证任意时刻只有一路高
4. **灵活调整**：修改 CMP_L/CMP_H 即可改变占空比
5. **死区保护**：两种方式都能实现完整的死区保护

---

## 总结

**核心机制：**
- 使用 **Up-Down 计数模式** 产生对称三角载波
- 通过 **两个比较值** (CMP_L, CMP_H) 划分三个区间
- 利用 **Action Qualifier** 在关键时刻切换输出
- 三路信号 **互补配合** 产生梯形波电压

**死区实现：**
- **方式一**：通过比较值间隔实现真正的"三路都关断"死区
- **方式二**：利用 DB_ACTV_HIC 互补模式的硬件死区特性

**波形生成流程：**
```
计数器 → 比较器 → AQ 模块 → 死区模块（可选）→ GPIO 输出
  ↓         ↓         ↓          ↓              ↓
0~1000   CMP_L/H   SET/CLEAR  延迟/互补      GA/G0/GB
```

这种方法充分利用了 F28379D EPWM 模块的硬件特性，实现了高精度、低开销的梯形波生成。
