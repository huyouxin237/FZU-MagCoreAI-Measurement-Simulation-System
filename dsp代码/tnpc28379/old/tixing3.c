//##########################
// TNPC Safe Test - Trapezoidal Waveform (No Hardware Dead-band)
// Rising: 29.5%, Hold: 41%, Falling: 29.5%
// 50kHz, GA/G0/GB all active
// GPIO0 and GPIO2 output same G0 signal (redundant)
// Dead-band: Implemented by CMP_L/CMP_H spacing (5 TBCLK = 50ns)
//##########################
#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

#define CARRIER     1000
#define CMP_L       295     // 29.5% rising
#define CMP_H       705     // 70.5% -> 29.5% falling
// Dead-band spacing: 295~300 and 700~705 = 5 TBCLK = 50ns

void ConfigureEPWM_Trapezoidal(void);
void SafetyCheck(void);

int main(void) {

    InitSysCtrl();
    memcpy((uint16_t *)&RamfuncsRunStart, (uint16_t *)&RamfuncsLoadStart, (unsigned long)&RamfuncsLoadSize);
    InitFlash();

    EALLOW;
    GpioCtrlRegs.GPBPUD.bit.GPIO36 = 1;
    GpioCtrlRegs.GPBMUX1.bit.GPIO36 = 0;
    GpioCtrlRegs.GPBDIR.bit.GPIO36 = 1;
    EDIS;

    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(100000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
    DELAY_US(100000);
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(100000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;

    SafetyCheck();

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    ClkCfgRegs.PERCLKDIVSEL.bit.EPWMCLKDIV = 1;
    EDIS;

    // GPIO mux: GPIO0 (G0), GPIO2 (G0 duplicate), GPIO6 (GB), GPIO11 (GA)
    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 1;  // EPWM1A

    GpioCtrlRegs.GPAPUD.bit.GPIO2  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO2  = 1;  // EPWM2A (same as GPIO0)

    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1;  // EPWM4A

    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1;  // EPWM6B
    EDIS;

    ConfigureEPWM_Trapezoidal();

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    EPwm1Regs.TBCTL.bit.SWFSYNC = 1;

    GpioDataRegs.GPBSET.bit.GPIO36 = 1;

    while(1)
    {
        DELAY_US(1000000);
    }

    return 0;
}

void SafetyCheck(void)
{
    if (CMP_L >= CMP_H) {
        while(1) {
            GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1;
            DELAY_US(50000);
        }
    }

    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(500000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
}

void ConfigureEPWM_Trapezoidal(void)
{
    // --- EPWM1A: G0 midpoint clamp (master) ---
    EPwm1Regs.TBCTR = 0;
    EPwm1Regs.TBPRD = CARRIER;
    EPwm1Regs.TBPHS.bit.TBPHS = 0;
    EPwm1Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm1Regs.TBCTL.bit.PHSEN    = TB_DISABLE;  // master
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

    // G0 HIGH between CMP_L and CMP_H
    EPwm1Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm1Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm1Regs.AQCTLA.bit.CBU = AQ_CLEAR;
    EPwm1Regs.AQCTLA.bit.CBD = AQ_SET;
    EPwm1Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    // Hardware dead-band DISABLED
    EPwm1Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // --- EPWM2A: G0 midpoint clamp (slave, same as EPWM1A) ---
    EPwm2Regs.TBCTR = 0;
    EPwm2Regs.TBPRD = CARRIER;
    EPwm2Regs.TBPHS.bit.TBPHS = 0;
    EPwm2Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm2Regs.TBCTL.bit.PHSEN    = TB_ENABLE;  // slave
    EPwm2Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm2Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm2Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm2Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm2Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm2Regs.CMPCTL.bit.SHDWBMODE = CC_SHADOW;
    EPwm2Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm2Regs.CMPCTL.bit.LOADBMODE = CC_CTR_ZERO;
    EPwm2Regs.CMPA.bit.CMPA = CMP_L;
    EPwm2Regs.CMPB.bit.CMPB = CMP_H;

    EPwm2Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm2Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm2Regs.AQCTLA.bit.CBU = AQ_CLEAR;
    EPwm2Regs.AQCTLA.bit.CBD = AQ_SET;
    EPwm2Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    // Hardware dead-band DISABLED
    EPwm2Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // --- EPWM4A: GB lower arm S3 ---
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = CARRIER;
    EPwm4Regs.TBPHS.bit.TBPHS = 0;
    EPwm4Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm4Regs.TBCTL.bit.PHSEN    = TB_ENABLE;  // slave
    EPwm4Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm4Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm4Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm4Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm4Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm4Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm4Regs.CMPA.bit.CMPA = CMP_H;

    // GB HIGH when counter > CMP_H
    EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    // Hardware dead-band DISABLED
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // --- EPWM6B: GA upper arm S1 ---
    EPwm6Regs.TBCTR = 0;
    EPwm6Regs.TBPRD = CARRIER;
    EPwm6Regs.TBPHS.bit.TBPHS = 0;
    EPwm6Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm6Regs.TBCTL.bit.PHSEN    = TB_ENABLE;  // slave
    EPwm6Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm6Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm6Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm6Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm6Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm6Regs.CMPA.bit.CMPA = CMP_L;

    // GA HIGH when counter < CMP_L
    EPwm6Regs.AQCTLB.bit.CAU = AQ_CLEAR;
    EPwm6Regs.AQCTLB.bit.CAD = AQ_SET;
    EPwm6Regs.AQCTLB.bit.ZRO = AQ_SET;

    // Hardware dead-band DISABLED
    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
}
