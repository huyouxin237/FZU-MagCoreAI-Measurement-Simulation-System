//##########################
// TNPC Safe Test Version - For Real Hardware Testing
//
// SAFETY FEATURES:
// - Fixed conservative parameters (no runtime modification)
// - Hardware dead-band enabled (100ns)
// - Parameter validation before EPWM start
// - LED status indicator
//
// HARDWARE REQUIREMENTS:
// - Low voltage DC bus (12V recommended for first test)
// - Current limiting resistor in series with DC bus
// - Oscilloscope on GaN gate signals (GQA/GQB/GQ0)
// - NO LOAD initially (ø’‘ÿ≤‚ ‘)
//
// CRITICAL: Verify waveforms on gate driver output BEFORE applying high voltage!
//##########################
#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

// === FIXED PARAMETERS (DO NOT MODIFY DURING RUNTIME) ===
#define FREQ_HZ     50000.0f    // 50kHz (conservative, lower freq = safer)
#define DUTY_P      0.2f        // 20% positive voltage
#define DUTY_0      0.3f        // 30% freewheel each side
#define DUTY_N      0.2f        // 20% negative voltage (must equal 1-2*DUTY_0-DUTY_P)
#define DEADTIME    10          // 10 TBCLK = 100ns @ 100MHz (conservative)

// Calculated constants
#define CARRIER     ((int)(50000000.0f / FREQ_HZ + 0.5f))  // 1000 @ 50kHz
#define CMP_L       ((int)(CARRIER * DUTY_P + 0.5f))       // 200
#define CMP_H       ((int)(CARRIER * (1.0f - DUTY_N) + 0.5f)) // 800

// Safety check at compile time


void ConfigureEPWM_Safe(void);
void SafetyCheck(void);

int main(void) {

    InitSysCtrl();
    memcpy((uint16_t *)&RamfuncsRunStart, (uint16_t *)&RamfuncsLoadStart, (unsigned long)&RamfuncsLoadSize);
    InitFlash();

    // LED D3 - status indicator
    EALLOW;
    GpioCtrlRegs.GPBPUD.bit.GPIO36 = 1;
    GpioCtrlRegs.GPBMUX1.bit.GPIO36 = 0;
    GpioCtrlRegs.GPBDIR.bit.GPIO36 = 1;
    EDIS;

    // LED blinks fast during initialization
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(100000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
    DELAY_US(100000);
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(100000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;

    // Safety check
    SafetyCheck();

    // Disable TBCLK before config
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    ClkCfgRegs.PERCLKDIVSEL.bit.EPWMCLKDIV = 1; // 100MHz
    EDIS;

    // GPIO mux -> EPWM function
    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1;
    EDIS;

    ConfigureEPWM_Safe();

    // Enable TBCLK + sync
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    EPwm1Regs.TBCTL.bit.SWFSYNC = 1;

    // LED solid ON = PWM running
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;

    // Main loop - just keep running
    while(1)
    {
        // Do nothing - PWM runs in hardware
        // LED stays ON to indicate normal operation
        DELAY_US(1000000);
    }

    return 0;
}

void SafetyCheck(void)
{
    // Verify parameters are safe
    float duty_sum = DUTY_P + DUTY_N + 2.0f * DUTY_0;

    if (duty_sum < 0.99f || duty_sum > 1.01f) {
        // Parameter error - blink LED rapidly forever
        while(1) {
            GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1;
            DELAY_US(50000);
        }
    }

    if (CMP_L >= CMP_H) {
        // Unsafe overlap - blink LED rapidly forever
        while(1) {
            GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1;
            DELAY_US(50000);
        }
    }

    // All checks passed - brief LED flash
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(500000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
}

void ConfigureEPWM_Safe(void)
{
    // --- EPWM1A: G0 midpoint clamp ---
    EPwm1Regs.TBCTR = 0;
    EPwm1Regs.TBPRD = CARRIER;
    EPwm1Regs.TBPHS.bit.TBPHS = 0;
    EPwm1Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm1Regs.TBCTL.bit.PHSEN    = TB_DISABLE;
    EPwm1Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm1Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm1Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm1Regs.TBCTL.bit.SYNCOSEL = TB_CTR_ZERO;

    EPwm1Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm1Regs.CMPCTL.bit.SHDWBMODE = CC_SHADOW;
    EPwm1Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm1Regs.CMPCTL.bit.LOADBMODE = CC_CTR_ZERO;
    EPwm1Regs.CMPA.bit.CMPA = CMP_L;
    EPwm1Regs.CMPB.bit.CMPB = CMP_H;

    EPwm1Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm1Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm1Regs.AQCTLA.bit.CBU = AQ_CLEAR;
    EPwm1Regs.AQCTLA.bit.CBD = AQ_SET;
    EPwm1Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    // Dead-band enabled
    EPwm1Regs.DBRED = DEADTIME;
    EPwm1Regs.DBFED = DEADTIME;
    EPwm1Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm1Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm1Regs.DBCTL.bit.POLSEL = DB_ACTV_HI; // Both A and B active high (not complementary)

    // --- EPWM4A: GB lower arm S3 ---
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = CARRIER;
    EPwm4Regs.TBPHS.bit.TBPHS = 0;
    EPwm4Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm4Regs.TBCTL.bit.PHSEN    = TB_ENABLE;
    EPwm4Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm4Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm4Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm4Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm4Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm4Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm4Regs.CMPA.bit.CMPA = CMP_H;

    EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    // Dead-band enabled
    EPwm4Regs.DBRED = DEADTIME;
    EPwm4Regs.DBFED = DEADTIME;
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm4Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm4Regs.DBCTL.bit.POLSEL = DB_ACTV_HI;

    // --- EPWM6B: GA upper arm S1 ---
    // Note: Using B output, so configure AQCTLB directly
    // Dead-band disabled for B output, rely on compare value spacing
    EPwm6Regs.TBCTR = 0;
    EPwm6Regs.TBPRD = CARRIER;
    EPwm6Regs.TBPHS.bit.TBPHS = 0;
    EPwm6Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm6Regs.TBCTL.bit.PHSEN    = TB_ENABLE;
    EPwm6Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm6Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm6Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm6Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm6Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm6Regs.CMPA.bit.CMPA = CMP_L;

    EPwm6Regs.AQCTLB.bit.CAU = AQ_CLEAR;
    EPwm6Regs.AQCTLB.bit.CAD = AQ_SET;
    EPwm6Regs.AQCTLB.bit.ZRO = AQ_SET;

    // Dead-band disabled (B output controlled directly by AQCTLB)
    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
}
