//##########################
// Phase 4: Adjustable Open-Loop Control
// Modify freq/duty_P/duty_0 in CCS Watch window to change waveform
//##########################
#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>
#include <math.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

// === Adjustable parameters (modify in CCS Watch window) ===
float freq   = 100000.0f;  // Hz
float duty_P = 0.3f;       // positive voltage duty
float duty_0 = 0.2f;       // freewheel duty (each side)
// duty_N is calculated: 1 - 2*duty_0 - duty_P

// === Internal calculated values (read-only in Watch) ===
int carrier;   // = 50MHz / freq = TBPRD
int CMP_L;     // = carrier * duty_P
int CMP_H;     // = carrier * (1 - duty_N)
float duty_N;

void ConfigureEPWM_3ch(void);
void UpdateEPWM(void);

int main(void) {

    InitSysCtrl();
    memcpy((uint16_t *)&RamfuncsRunStart, (uint16_t *)&RamfuncsLoadStart, (unsigned long)&RamfuncsLoadSize);
    InitFlash();

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    ClkCfgRegs.PERCLKDIVSEL.bit.EPWMCLKDIV = 1; // EPWMCLK = 100MHz
    EDIS;

    // LED D3
    EALLOW;
    GpioCtrlRegs.GPBPUD.bit.GPIO36 = 1;
    GpioCtrlRegs.GPBMUX1.bit.GPIO36 = 0;
    GpioCtrlRegs.GPBDIR.bit.GPIO36 = 1;
    EDIS;

    // GPIO mux -> EPWM function
    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 1; // EPWM1A
    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1; // EPWM4A
    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1; // EPWM6BEDIS;


    // Initial parameter calculation
    duty_N  = 1.0f - 2.0f * duty_0 - duty_P;
    carrier = (int)(50000000.0f / freq + 0.5f);
    CMP_L   = (int)(carrier * duty_P + 0.5f);
    CMP_H   = (int)(carrier * (1.0f - duty_N) + 0.5f);

    ConfigureEPWM_3ch();

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    EPwm1Regs.TBCTL.bit.SWFSYNC = 1;

    while(1)
    {
        // Recalculate and update registers every loop
        duty_N  = 1.0f - 2.0f * duty_0 - duty_P;
        carrier = (int)(50000000.0f / freq + 0.5f);
        CMP_L   = (int)(carrier * duty_P + 0.5f);
        CMP_H   = (int)(carrier * (1.0f - duty_N) + 0.5f);

        UpdateEPWM();

        DELAY_US(10000); // update every 10ms
        GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1;
    }

    return 0;
}

void UpdateEPWM(void)
{
    EPwm1Regs.TBPRD = carrier;
    EPwm4Regs.TBPRD = carrier;
    EPwm6Regs.TBPRD = carrier;

    if (CMP_L >= CMP_H) {
        // Unsafe: disable G0 (keep GA and GB only, no freewheel)
        EPwm1Regs.AQCTLA.bit.CAU = AQ_NO_ACTION;
        EPwm1Regs.AQCTLA.bit.CAD = AQ_NO_ACTION;
        EPwm1Regs.AQCTLA.bit.CBU = AQ_NO_ACTION;
        EPwm1Regs.AQCTLA.bit.CBD = AQ_NO_ACTION;} else {
        EPwm1Regs.AQCTLA.bit.CAU = AQ_SET;
        EPwm1Regs.AQCTLA.bit.CAD = AQ_CLEAR;
        EPwm1Regs.AQCTLA.bit.CBU = AQ_CLEAR;
        EPwm1Regs.AQCTLA.bit.CBD = AQ_SET;
        EPwm1Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    }

    EPwm1Regs.CMPA.bit.CMPA = CMP_L;
    EPwm1Regs.CMPB.bit.CMPB = CMP_H;
    EPwm4Regs.CMPA.bit.CMPA = CMP_H;
    EPwm6Regs.CMPA.bit.CMPA = CMP_L;
}

void ConfigureEPWM_3ch(void)
{
    // --- EPWM1A: G0 midpoint clamp ---
    EPwm1Regs.TBCTR = 0;
    EPwm1Regs.TBPRD = carrier;
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
    EPwm1Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // --- EPWM4A: GB lower arm S3 ---
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = carrier;
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
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // --- EPWM6B: GA upper arm S1 ---
    EPwm6Regs.TBCTR = 0;
    EPwm6Regs.TBPRD = carrier;
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
    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
}
