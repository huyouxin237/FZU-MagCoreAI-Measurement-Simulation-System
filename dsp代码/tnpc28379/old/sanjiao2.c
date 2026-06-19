//##########################
// TNPC Safe Test - Asymmetric Triangular Waveform
// Rising: 54.5%, Falling: 44.5%, Dead-time: 1% (200ns total)
// 50kHz, only GA and GB active
//##########################
#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

#define CARRIER     1000
#define CMP_L       395     // 54.5% rising (close to 55%)
#define CMP_H       405     // 55.5% -> 44.5% falling (close to 45%)
#define DEADTIME    10      // 100ns hardware dead-band

void ConfigureEPWM_Asymmetric(void);
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

    // GPIO mux: only GPIO6 and GPIO11
    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO0  = 1;

    GpioCtrlRegs.GPAPUD.bit.GPIO2  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO2  = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO2  = 1;

    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1;

    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1;
    EDIS;

    GpioDataRegs.GPACLEAR.bit.GPIO0 = 1;
    GpioDataRegs.GPACLEAR.bit.GPIO2 = 1;

    ConfigureEPWM_Asymmetric();

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    EPwm4Regs.TBCTL.bit.SWFSYNC = 1;

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

void ConfigureEPWM_Asymmetric(void)
{
    // --- EPWM4A: GB lower arm S3 ---
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = CARRIER;
    EPwm4Regs.TBPHS.bit.TBPHS = 0;
    EPwm4Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm4Regs.TBCTL.bit.PHSEN    = TB_DISABLE;
    EPwm4Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm4Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm4Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm4Regs.TBCTL.bit.SYNCOSEL = TB_CTR_ZERO;

    EPwm4Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm4Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm4Regs.CMPA.bit.CMPA = CMP_H;

    EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;

    EPwm4Regs.DBRED = DEADTIME;
    EPwm4Regs.DBFED = DEADTIME;
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm4Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm4Regs.DBCTL.bit.POLSEL = DB_ACTV_HI;

    // --- EPWM6B: GA upper arm S1 ---
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

    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
}
