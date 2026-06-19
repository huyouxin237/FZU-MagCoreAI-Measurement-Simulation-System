//##########################
// 40% Rising, 20% Hold, 20% Falling, 20% Hold (Repeated Every Cycle)
// Using CMPA interrupt on both up and down counting
//##########################
#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

#define CARRIER     1000
#define DEADTIME    10

volatile int g0_state = 0;

void ConfigureEPWM_Repeated(void);
void SafetyCheck(void);
__interrupt void epwm1_isr(void);

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

    DINT;
    InitPieCtrl();
    IER = 0x0000;
    IFR = 0x0000;
    InitPieVectTable();

    EALLOW;
    PieVectTable.EPWM1_INT = &epwm1_isr;
    EDIS;

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    ClkCfgRegs.PERCLKDIVSEL.bit.EPWMCLKDIV = 1;
    EDIS;

    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 1;

    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1;

    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0;
    GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1;
    EDIS;

    ConfigureEPWM_Repeated();

    IER |= M_INT3;
    PieCtrlRegs.PIEIER3.bit.INTx1 = 1;
    EINT;
    ERTM;

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
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(500000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
}

void ConfigureEPWM_Repeated(void)
{
    // --- EPWM1A: G0 with ISR control ---
    EPwm1Regs.TBCTR = 0;
    EPwm1Regs.TBPRD = CARRIER;
    EPwm1Regs.TBPHS.bit.TBPHS = 0;
    EPwm1Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm1Regs.TBCTL.bit.PHSEN    = TB_DISABLE;
    EPwm1Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm1Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm1Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm1Regs.TBCTL.bit.SYNCOSEL = TB_CTR_ZERO;

    EPwm1Regs.CMPCTL.bit.SHDWAMODE = CC_IMMEDIATE;
    EPwm1Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm1Regs.CMPA.bit.CMPA = 400;

    EPwm1Regs.AQCTLA.bit.CAU = AQ_NO_ACTION;
    EPwm1Regs.AQCTLA.bit.CAD = AQ_NO_ACTION;
    EPwm1Regs.AQCTLA.bit.ZRO = AQ_NO_ACTION;

    EPwm1Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // Interrupt on counter = CMPA (both up and down)
    EPwm1Regs.ETSEL.bit.INTSEL = ET_CTR_CMPA;  // Both directions
    EPwm1Regs.ETSEL.bit.INTEN = 1;
    EPwm1Regs.ETPS.bit.INTPRD = ET_1ST;

    // --- EPWM4A: GB (60-80% in up phase, 20-40% in down phase) ---
    // Controlled by ISR, disable AQ
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = CARRIER;
    EPwm4Regs.TBPHS.bit.TBPHS = 0;
    EPwm4Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm4Regs.TBCTL.bit.PHSEN    = TB_ENABLE;
    EPwm4Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm4Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm4Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm4Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm4Regs.AQCTLA.bit.CAU = AQ_NO_ACTION;
    EPwm4Regs.AQCTLA.bit.CAD = AQ_NO_ACTION;
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_NO_ACTION;

    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;

    // --- EPWM6B: GA (0-40% in up phase, 60-100% in down phase) ---
    // Controlled by ISR, disable AQ
    EPwm6Regs.TBCTR = 0;
    EPwm6Regs.TBPRD = CARRIER;
    EPwm6Regs.TBPHS.bit.TBPHS = 0;
    EPwm6Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm6Regs.TBCTL.bit.PHSEN    = TB_ENABLE;
    EPwm6Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm6Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm6Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;

    EPwm6Regs.AQCTLB.bit.CAU = AQ_NO_ACTION;
    EPwm6Regs.AQCTLB.bit.CAD = AQ_NO_ACTION;
    EPwm6Regs.AQCTLB.bit.ZRO = AQ_NO_ACTION;

    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_DISABLE;
}

__interrupt void epwm1_isr(void)
{
    // Check counter direction
    int is_counting_up = (EPwm1Regs.TBSTS.bit.CTRDIR == 0);  // 0=down, 1=up

    if (is_counting_up) {
        // Up phase: 0-400 GA, 400-600 G0, 600-800 GB, 800-1000 G0
        switch(g0_state) {
            case 0:  // At 400, enter first hold
                EPwm1Regs.AQCSFRC.bit.CSFA = 2;  // G0 HIGH
                EPwm6Regs.AQSFRC.bit.ACTSFA = 1;  // GA LOW
                EPwm4Regs.AQSFRC.bit.ACTSFA = 1;  // GB LOW
                EPwm1Regs.CMPA.bit.CMPA = 600;
                g0_state = 1;
                break;

            case 1:  // At 600, exit first hold, enter falling
                EPwm1Regs.AQCSFRC.bit.CSFA = 1;  // G0 LOW
                EPwm4Regs.AQSFRC.bit.ACTSFA = 2;  // GB HIGH
                EPwm1Regs.CMPA.bit.CMPA = 800;
                g0_state = 2;
                break;

            case 2:  // At 800, exit falling, enter second hold
                EPwm1Regs.AQCSFRC.bit.CSFA = 2;  // G0 HIGH
                EPwm4Regs.AQSFRC.bit.ACTSFA = 1;  // GB LOW
                EPwm1Regs.CMPA.bit.CMPA = 800;  // Stay at 800 for down phase
                g0_state = 3;
                break;
        }
    } else {
        // Down phase: repeat same voltage sequence
        // 1000-800 GA, 800-600 G0, 600-400 GB, 400-0 G0
        switch(g0_state) {
            case 3:  // At 800 (down), exit second hold, enter rising
                EPwm1Regs.AQCSFRC.bit.CSFA = 1;  // G0 LOW
                EPwm6Regs.AQSFRC.bit.ACTSFA = 2;  // GA HIGH
                EPwm1Regs.CMPA.bit.CMPA = 600;
                g0_state = 4;
                break;

            case 4:  // At 600 (down), exit rising, enter first hold
                EPwm1Regs.AQCSFRC.bit.CSFA = 2;  // G0 HIGH
                EPwm6Regs.AQSFRC.bit.ACTSFA = 1;  // GA LOW
                EPwm1Regs.CMPA.bit.CMPA = 400;
                g0_state = 5;
                break;

            case 5:  // At 400 (down), exit first hold, enter falling
                EPwm1Regs.AQCSFRC.bit.CSFA = 1;  // G0 LOW
                EPwm4Regs.AQSFRC.bit.ACTSFA = 2;  // GB HIGH
                EPwm1Regs.CMPA.bit.CMPA = 400;  // Stay at 400 for next up phase
                g0_state = 6;
                break;

            case 6:  // Near 0, enter second hold
                if (EPwm1Regs.TBCTR < 50) {  // Near zero
                    EPwm1Regs.AQCSFRC.bit.CSFA = 2;  // G0 HIGH
                    EPwm4Regs.AQSFRC.bit.ACTSFA = 1;  // GB LOW
                    g0_state = 0;  // Reset for next up phase
                }
                break;
        }
    }

    EPwm1Regs.ETCLR.bit.INT = 1;
    PieCtrlRegs.PIEACK.all = PIEACK_GROUP3;
}
