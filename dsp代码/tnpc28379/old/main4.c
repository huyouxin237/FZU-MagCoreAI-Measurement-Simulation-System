//##########################
// Phase 5: UART + Python Automated Sweep
// SCI-A communication + triple nested loop (duty_0 x duty_P x freq)
//##########################
#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>
#include <math.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

// === Sweep parameters ===
float Dstep = 0.1f;
float D0min = 0.0f;
float D0max = 0.4f;
float Fmin = 50000.0f;   // 50kHz
float Fmax = 510000.0f;  // 510kHz
float Fpointsperdecade = 10.0f;

// === Current values ===
float freq, duty_P, duty_0, duty_N;
int carrier, CMP_L, CMP_H;
int d0_int, dP_int, freqidx;

void ConfigureEPWM_3ch(void);
void UpdateEPWM(void);
void scia_init(void);
void scia_xmit(int a);
Uint16 scia_recv(void);

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
    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1; // EPWM6B
    EDIS;

    // GPIO28/29 -> SCI-A
    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO28 = 0;
    GpioCtrlRegs.GPAMUX2.bit.GPIO28 = 1; // SCI-A RX
    GpioCtrlRegs.GPADIR.bit.GPIO28 = 0;  // input

    GpioCtrlRegs.GPAPUD.bit.GPIO29 = 0;
    GpioCtrlRegs.GPAMUX2.bit.GPIO29 = 1; // SCI-A TX
    GpioCtrlRegs.GPADIR.bit.GPIO29 = 1;  // output
    EDIS;

    // Init SCI-A
    scia_init();

    // Init EPWM (dummy values)
    freq = 100000.0f;
    duty_P = 0.3f;
    duty_0 = 0.2f;
    duty_N = 1.0f - 2.0f * duty_0 - duty_P;
    carrier = (int)(50000000.0f / freq + 0.5f);
    CMP_L = (int)(carrier * duty_P + 0.5f);
    CMP_H = (int)(carrier * (1.0f - duty_N) + 0.5f);
    ConfigureEPWM_3ch();

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    EPwm1Regs.TBCTL.bit.SWFSYNC = 1;

    // === Triple nested sweep loop ===
    while(1)
    {
        for(duty_0 = D0min; duty_0 <= D0max + Dstep*0.5f; duty_0 += Dstep)
        {
            d0_int = (int)(duty_0 * 100.0f + 0.5f);

            // Wait for Python handshake
            scia_recv();
            // Echo back d0_int
            scia_xmit(d0_int);

            for(duty_P = Dstep; duty_P <= 1.0f - 2.0f*duty_0 - Dstep + Dstep*0.5f; duty_P += Dstep)
            {
                dP_int = (int)(duty_P * 100.0f + 0.5f);
                duty_N = 1.0f - 2.0f * duty_0 - duty_P;

                // Wait for Python handshake
                scia_recv();
                // Echo back dP_int
                scia_xmit(dP_int);

                for(freqidx = 3 * (int)Fpointsperdecade; freqidx <= 7 * (int)Fpointsperdecade; freqidx++)
                {
                    float logF = (float)freqidx / Fpointsperdecade;
                    freq = powf(10.0f, logF);

                    if(freq < Fmin || freq > Fmax) continue;

                    // Wait for Python handshake
                    scia_recv();
                    // Echo back freqidx
                    scia_xmit(freqidx);

                    // Update EPWM
                    carrier = (int)(50000000.0f / freq + 0.5f);
                    CMP_L = (int)(carrier * duty_P + 0.5f);
                    CMP_H = (int)(carrier * (1.0f - duty_N) + 0.5f);
                    UpdateEPWM();

                    GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1; // LED blink
                }
            }
        }
    }

    return 0;
}

void UpdateEPWM(void)
{
    EPwm1Regs.TBPRD = carrier;
    EPwm4Regs.TBPRD = carrier;
    EPwm6Regs.TBPRD = carrier;

    if (CMP_L >= CMP_H) {
        EPwm1Regs.AQCTLA.bit.CAU = AQ_NO_ACTION;
        EPwm1Regs.AQCTLA.bit.CAD = AQ_NO_ACTION;
        EPwm1Regs.AQCTLA.bit.CBU = AQ_NO_ACTION;
        EPwm1Regs.AQCTLA.bit.CBD = AQ_NO_ACTION;
    } else {
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
    // EPWM1A: G0 midpoint clamp
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

    // EPWM4A: GB lower arm S3
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

    // EPWM6B: GA upper arm S1
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

void scia_init(void)
{
    SciaRegs.SCICCR.all = 0x0007;  // 8 bits, no parity, 1 stop bit
    SciaRegs.SCICTL1.all = 0x0003; // enable TX, RX
    SciaRegs.SCICTL2.all = 0x0003;
    SciaRegs.SCICTL2.bit.TXINTENA = 1;
    SciaRegs.SCICTL2.bit.RXBKINTENA = 1;

    // 4800 baud @ LSPCLK = 50MHz (200MHz SYSCLK / 4)
    SciaRegs.SCIHBAUD.all = 0x0005;
    SciaRegs.SCILBAUD.all = 0x0016;

    SciaRegs.SCIFFTX.all = 0xE040;
    SciaRegs.SCIFFRX.all = 0x2044;
    SciaRegs.SCIFFCT.all = 0x0;

    SciaRegs.SCICTL1.all = 0x0023; // Release from reset
}

void scia_xmit(int a)
{
    while(SciaRegs.SCIFFTX.bit.TXFFST != 0) {} // wait for TX FIFO empty
    SciaRegs.SCITXBUF.all = a;
}

Uint16 scia_recv(void)
{
    SciaRegs.SCIFFRX.bit.RXFIFORESET = 0;
    SciaRegs.SCIFFRX.bit.RXFIFORESET = 1;
    while(SciaRegs.SCIFFRX.bit.RXFFST != 1) {} // wait for 1 byte
    return SciaRegs.SCIRXBUF.all;
}
