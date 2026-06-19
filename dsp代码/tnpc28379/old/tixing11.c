//##########################
// TNPC Safe Test - Trapezoidal Waveform
// Rising: 29.5%, Hold: 40%, Falling: 29.5%, Dead-time: 1%
// 50kHz, GA/G0/GB all active
// GPIO0 and GPIO2 output same G0 signal (redundant)
//##########################

#include "F28x_Project.h"   // TI DSP 常用头文件，包含外设寄存器定义
#include <string.h>         // 内存操作函数（用于 memcpy）
#include <stdint.h>         // 标准整数类型

// 从链接器命令文件中引用的段，用于将 Flash 中的函数复制到 RAM 运行
extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

// 定义 PWM 相关常数
#define CARRIER     1000    // PWM 周期计数值（向上-向下计数模式下对应 50kHz）
#define CMP_L       300     // 比较值低点（30% 占空比，上升段终点）
#define CMP_H       700     // 比较值高点（70% 位置，对应下降段 30%）
#define DEADTIME    10      // 硬件死区时间（100ns，根据系统时钟计算）

// 函数声明
void ConfigureEPWM_Trapezoidal(void);
void SafetyCheck(void);

int main(void) {

    // 初始化系统控制：时钟、PLL、外设时钟等
    InitSysCtrl();

    // 将 Flash 中的一些函数（如 Flash 初始化代码）复制到 RAM 中运行以提高速度
    memcpy((uint16_t *)&RamfuncsRunStart,
           (uint16_t *)&RamfuncsLoadStart,
           (unsigned long)&RamfuncsLoadSize);

    // 初始化 Flash 等待状态等
    InitFlash();

    // 配置 GPIO36 作为简单指示输出（用于程序状态指示）
    EALLOW;  // 允许访问受保护的寄存器
    GpioCtrlRegs.GPBPUD.bit.GPIO36 = 1;   // 禁用内部上拉
    GpioCtrlRegs.GPBMUX1.bit.GPIO36 = 0;  // 设置为通用 GPIO 功能
    GpioCtrlRegs.GPBDIR.bit.GPIO36 = 1;   // 设置为输出
    EDIS;    // 禁止访问受保护寄存器

    // 闪烁 GPIO36 几次，作为启动指示
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;   // 拉高
    DELAY_US(500000);                     // 延时 500ms
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1; // 拉低
    DELAY_US(500000);
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(500000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;

    // 执行安全检查（判断 CMP_L 和 CMP_H 是否错误）
    SafetyCheck();

    // 禁止所有 ePWM 的时钟同步，以便单独配置各模块
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;   // 停止 ePWM 时基时钟同步
    ClkCfgRegs.PERCLKDIVSEL.bit.EPWMCLKDIV = 1; // 配置 ePWM 时钟分频（此处为 1 分频）
    EDIS;

    // 配置 GPIO 复用功能，将引脚映射到 ePWM 输出
    EALLOW;
    // GPIO0 -> EPWM1A   (G0 主信号)
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0;      // 使能上拉（0=使能）
    GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 1;     // 复用为 EPWM1A

    // GPIO2 -> EPWM2A   (G0 冗余信号，与 GPIO0 相同)
    GpioCtrlRegs.GPAPUD.bit.GPIO2  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO2  = 1;     // 复用为 EPWM2A

    // GPIO6 -> EPWM4A   (GB 下臂 S3)
    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1;     // 复用为 EPWM4A

    // GPIO11 -> EPWM6B  (GA 上臂 S1)
    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1;     // 复用为 EPWM6B
    EDIS;

    // 配置所有 ePWM 模块的参数（比较值、动作、死区等）
    ConfigureEPWM_Trapezoidal();

    // 恢复 ePWM 时基时钟同步，所有模块将同时开始计数
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    EPwm1Regs.TBCTL.bit.SWFSYNC = 1;         // 产生一次软件同步，对齐所有从模块

    // 将 GPIO36 拉高，表示配置完成、程序正常运行
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;

    // 主循环：空转，仅保持程序运行
    while(1)
    {
        DELAY_US(1000000);   // 延时 1 秒（可在此加入其它任务）
    }

    return 0;
}

// 安全检测函数：如果 CMP_L >= CMP_H，则进入无限循环并闪烁 LED 报错
void SafetyCheck(void)
{
    if (CMP_L >= CMP_H) {                     // 正常情况下 CMP_L (300) < CMP_H (700)
        while(1) {
            GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1;  // 翻转 GPIO36
            DELAY_US(500000);                         // 500ms 闪烁
        }
    }

    // 无错误：短暂亮灯后熄灭，表示安全通过
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(500000);        // 500ms
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
}

// 配置所有 ePWM 模块，产生梯形波所需的 G0、GA、GB 信号
void ConfigureEPWM_Trapezoidal(void)
{
    // ========== EPWM1A : G0 中点钳位信号（主模块） ==========
    EPwm1Regs.TBCTR = 0;                         // 清除时基计数器
    EPwm1Regs.TBPRD = CARRIER;                   // 周期 = 1000
    EPwm1Regs.TBPHS.bit.TBPHS = 0;               // 相位寄存器为 0
    EPwm1Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN; // 向上-向下计数（中心对齐）
    EPwm1Regs.TBCTL.bit.PHSEN    = TB_DISABLE;   // 作为主模块，禁止相位同步输入
    EPwm1Regs.TBCTL.bit.PRDLD    = TB_SHADOW;    // 周期寄存器使用影子模式，在周期边界加载
    EPwm1Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;     // 高速外设时钟分频 1
    EPwm1Regs.TBCTL.bit.CLKDIV   = TB_DIV1;      // 时基时钟分频 1
    EPwm1Regs.TBCTL.bit.SYNCOSEL = TB_CTR_ZERO;  // 计数器归零时输出同步信号给从模块

    // 比较寄存器配置：使用影子模式，在计数器归零时加载
    EPwm1Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm1Regs.CMPCTL.bit.SHDWBMODE = CC_SHADOW;
    EPwm1Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm1Regs.CMPCTL.bit.LOADBMODE = CC_CTR_ZERO;
    EPwm1Regs.CMPA.bit.CMPA = CMP_L;             // CMPA = 300
    EPwm1Regs.CMPB.bit.CMPB = CMP_H;             // CMPB = 700

    // 动作限定器：产生 G0 信号，在 CMP_L 到 CMP_H 之间为高
    EPwm1Regs.AQCTLA.bit.CAU = AQ_SET;           // 计数上升到达 CMPA 时置高
    EPwm1Regs.AQCTLA.bit.CAD = AQ_CLEAR;         // 计数下降到达 CMPA 时清零
    EPwm1Regs.AQCTLA.bit.CBU = AQ_CLEAR;         // 上升到达 CMPB 时清零
    EPwm1Regs.AQCTLA.bit.CBD = AQ_SET;           // 下降到达 CMPB 时置高
    EPwm1Regs.AQCTLA.bit.ZRO = AQ_CLEAR;         // 计数器归零时清零

    // 死区配置：上升沿延迟 DEADTIME，下降沿延迟 DEADTIME
    EPwm1Regs.DBRED = DEADTIME;
    EPwm1Regs.DBFED = DEADTIME;
    EPwm1Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE; // 完全使能死区（输出 A 和 B 均为带死区的互补对）
    EPwm1Regs.DBCTL.bit.IN_MODE = DBA_ALL;         // 以 EPWMxA 为输入源
    EPwm1Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;       // 不反转极性，高电平有效

    // ========== EPWM2A : G0 相同信号（从模块，冗余输出） ==========
    EPwm2Regs.TBCTR = 0;
    EPwm2Regs.TBPRD = CARRIER;
    EPwm2Regs.TBPHS.bit.TBPHS = 0;                // 相位寄存器 0，但与主模块同步
    EPwm2Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm2Regs.TBCTL.bit.PHSEN    = TB_ENABLE;     // 从模式，接收同步信号
    EPwm2Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm2Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm2Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm2Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;    // 同步输出选择为直接传递输入同步信号

    EPwm2Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm2Regs.CMPCTL.bit.SHDWBMODE = CC_SHADOW;
    EPwm2Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm2Regs.CMPCTL.bit.LOADBMODE = CC_CTR_ZERO;
    EPwm2Regs.CMPA.bit.CMPA = CMP_L;
    EPwm2Regs.CMPB.bit.CMPB = CMP_H;

    // 动作配置与 EPWM1 完全相同
    EPwm2Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm2Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm2Regs.AQCTLA.bit.CBU = AQ_CLEAR;
    EPwm2Regs.AQCTLA.bit.CBD = AQ_SET;
    EPwm2Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    // 同样使能死区，参数与主模块一致
    EPwm2Regs.DBRED = DEADTIME;
    EPwm2Regs.DBFED = DEADTIME;
    EPwm2Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm2Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm2Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

    // ========== EPWM4A : GB 下臂信号 S3 ==========
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = CARRIER;
    EPwm4Regs.TBPHS.bit.TBPHS = 0;
    EPwm4Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm4Regs.TBCTL.bit.PHSEN    = TB_ENABLE;    // 作为从模块接收同步
    EPwm4Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm4Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm4Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm4Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm4Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm4Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm4Regs.CMPA.bit.CMPA = CMP_H;             // GB 的比较值为 CMP_H (700)

    // GB 信号：当计数器 > CMP_H 时为高（即下降到 CMP_H 以下时清零）
    EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;           // 上升到达 CMPA 时置高
    EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;         // 下降到达 CMPA 时清零
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;         // 归零时清零

    // 死区使能
    EPwm4Regs.DBRED = DEADTIME;
    EPwm4Regs.DBFED = DEADTIME;
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm4Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm4Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

    // ========== EPWM6B : GA 上臂信号 S1 ==========
    EPwm6Regs.TBCTR = 0;                                    // 计数器从 0 开始
    EPwm6Regs.TBPRD = CARRIER;                              // 周期寄存器的值
    EPwm6Regs.TBPHS.bit.TBPHS = 0;                          // 无相位偏移
    EPwm6Regs.TBCTL.bit.CTRMODE = TB_COUNT_UPDOWN;          // 增减计数模式, 生成对称 PWM
    EPwm6Regs.TBCTL.bit.PHSEN = TB_ENABLE;                 // 使能相位同步, 本模块作为从模块
    EPwm6Regs.TBCTL.bit.PRDLD = TB_SHADOW;                  // 使用影子寄存器, 周期更新更平滑
    EPwm6Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;                // 高速时钟分频系数: /1
    EPwm6Regs.TBCTL.bit.CLKDIV = TB_DIV1;                   // 时钟分频系数: /1
    EPwm6Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;             //  同步输入来自上一级

    // 2. 比较器 (CC) 子模块配置
    EPwm6Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;             // CMPA 寄存器使用影子模式
    EPwm6Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;           // 计数器归零时, 从影子寄存器加载 CMPA 值
    EPwm6Regs.CMPA.bit.CMPA = CMP_L;                        // 设置 CMPA 的值 (由 CMP_L 决定, 即 EPWMxA 的跳变点)

    // 3. 动作限定器 (AQ) 子模块配置——仅配置 EPWM6A
    EPwm6Regs.AQCTLA.bit.CAU = AQ_SET;                      // 在增减计数模式下, 上升沿到达 CMPA 时, 将 EPWM6A 置为高电平
    EPwm6Regs.AQCTLA.bit.CAD = AQ_CLEAR;                    // 在增减计数模式下, 下降沿到达 CMPA 时, 将 EPWM6A 置为低电平
    EPwm6Regs.AQCTLA.bit.ZRO = AQ_CLEAR;                    // 计数器归零时, 将 EPWM6A 置为高电平
    EPwm6Regs.AQCTLA.bit.PRD = AQ_SET;                    // 计数器等于周期值时, 将 EPWM6A 置为低电平

    // 4. 死区 (DB) 子模块配置——核心: 由 EPWM6A 生成互补的 EPWM6B
    EPwm6Regs.DBRED = DEADTIME;                             // 上升沿死区时间, 单位: TBCLK 周期数 (默认 TBCLK = SYSCLK)
    EPwm6Regs.DBFED = DEADTIME;                             // 下降沿死区时间, 单位: TBCLK 周期数
    EPwm6Regs.DBCTL.bit.IN_MODE = DBA_ALL;                  // 以 EPWMxA 为两个通道的输入源
    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;          // 完全使能死区, A 和 B 都输出
    EPwm6Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;               // 高电平有效, 互补, 输出极性为 ACTIVE_HI 互补



}
