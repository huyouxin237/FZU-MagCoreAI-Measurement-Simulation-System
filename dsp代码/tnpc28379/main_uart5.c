//##########################
// TNPC UART Control - main_uart5.c
// Based on main_uart4.c:
//   - Baud rate 115200 -> 4800 (rollback for reliability;
//     faster baud caused race-condition NAK errors due to
//     host-side read/write timing jitter)
//   - ProcessUART rewritten: v3-style "wait for full 5-byte frame"
//     but with a proper re-sync loop that keeps consuming bytes until
//     0xAA is found. Avoids v3's misalignment bug (left 4 stale bytes)
//     and v5's earlier busy-wait risk after finding the header.
//
// GPIO0  (EPWM1A) -> G0 midpoint clamp
// GPIO2  (EPWM2A) -> G0 redundant
// GPIO6  (EPWM4A) -> GB lower arm S3
// GPIO11 (EPWM6B) -> GA upper arm S1
// GPIO28 (SCI-A RX) <- CH340 TX
// GPIO29 (SCI-A TX) -> CH340 RX
//
// Protocol: [0xAA][CMD][VAL_H][VAL_L][CHK]
// DSP replies: 0x06=ACK, 0x15=NAK
//##########################

#include "F28x_Project.h"
#include <string.h>
#include <stdint.h>

extern Uint16 RamfuncsLoadStart;
extern Uint16 RamfuncsLoadSize;
extern Uint16 RamfuncsRunStart;

// === Runtime parameters (updated via UART) ===
volatile Uint16 carrier  = 1000;  // TBPRD, 50kHz default
volatile Uint16 cmp_l    = 200;   // duty_P compare value
volatile Uint16 cmp_h    = 600;   // duty_N compare value
volatile Uint16 deadtime = 10;    // dead-band TBCLK counts
volatile Uint16 pwm_running = 0;  // 0=stopped, 1=running

// Staging area for new parameters (applied on CMD 0x10)
Uint16 new_carrier  = 1000;
Uint16 new_cmp_l    = 200;
Uint16 new_cmp_h    = 600;
Uint16 new_deadtime = 10;

// Protocol constants
#define FRAME_HEADER 0xAA
#define CMD_SET_CARRIER  0x01
#define CMD_SET_CMP_L    0x02
#define CMD_SET_CMP_H    0x03
#define CMD_SET_DEADTIME 0x04
#define CMD_SET_MODE     0x05
#define CMD_APPLY        0x10
#define CMD_STOP_PWM     0x20
#define CMD_START_PWM    0x21
#define ACK 0x06
#define NAK 0x15

// Mode state
#define MODE_TRAPEZOIDAL 0
#define MODE_TRIANGULAR  1

volatile Uint16 current_mode = MODE_TRAPEZOIDAL;
Uint16 new_mode = MODE_TRAPEZOIDAL;

// Function declarations
void ConfigureEPWM_Trapezoidal(void);
void ConfigureEPWM_Triangular(void);
void UpdateEPWM_Params(void);
void StopPWM(void);
void StartPWM(void);
void SafetyCheck(void);
void scia_init(void);
void scia_fifo_init(void);
void scia_xmit(int a);
Uint16 scia_recv(void);
void ProcessUART(void);

// New helpers
static void ReconfigureToTrapezoidal(void);
static void ReconfigureToTriangular(void);
static void SyncCurrentMode(void);
static void ShadowUpdateTrapezoidal(void);
static void ShadowUpdateTriangular(void);

int main(void) {

    InitSysCtrl();
    memcpy((uint16_t *)&RamfuncsRunStart,
           (uint16_t *)&RamfuncsLoadStart,
           (unsigned long)&RamfuncsLoadSize);
    InitFlash();

    // LED D3 (GPIO36)
    EALLOW;
    GpioCtrlRegs.GPBPUD.bit.GPIO36 = 1;
    GpioCtrlRegs.GPBMUX1.bit.GPIO36 = 0;
    GpioCtrlRegs.GPBDIR.bit.GPIO36 = 1;
    EDIS;

    // Init blink
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(200000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
    DELAY_US(200000);
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(200000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;

    // SCI-A GPIO config (GPIO28=RX, GPIO29=TX)
    EALLOW;
    GpioCtrlRegs.GPAMUX2.bit.GPIO28 = 1;  // SCI-A RX
    GpioCtrlRegs.GPAPUD.bit.GPIO28 = 0;   // enable pull-up
    GpioCtrlRegs.GPADIR.bit.GPIO28 = 0;   // input
    GpioCtrlRegs.GPAMUX2.bit.GPIO29 = 1;  // SCI-A TX
    GpioCtrlRegs.GPAPUD.bit.GPIO29 = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO29 = 1;   // output
    EDIS;

    // Init SCI-A
    scia_fifo_init();
    scia_init();

    // Disable TBCLK before config
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    ClkCfgRegs.PERCLKDIVSEL.bit.EPWMCLKDIV = 1; // 100MHz
    EDIS;

    // GPIO mux -> EPWM function
    EALLOW;
    GpioCtrlRegs.GPAPUD.bit.GPIO0  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO0  = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO2  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO2  = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO6  = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO6  = 1;
    GpioCtrlRegs.GPAPUD.bit.GPIO11 = 0; GpioCtrlRegs.GPAMUX1.bit.GPIO11 = 1;
    EDIS;

    // Configure EPWM with default params
    if (cmp_l == cmp_h) {
        EALLOW;
        GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 0;
        GpioCtrlRegs.GPADIR.bit.GPIO0 = 1;
        GpioDataRegs.GPACLEAR.bit.GPIO0 = 1;
        GpioCtrlRegs.GPAMUX1.bit.GPIO2 = 0;
        GpioCtrlRegs.GPADIR.bit.GPIO2 = 1;
        GpioDataRegs.GPACLEAR.bit.GPIO2 = 1;
        EDIS;
        ConfigureEPWM_Triangular();
        current_mode = MODE_TRIANGULAR;
        new_mode = MODE_TRIANGULAR;
    } else {
        ConfigureEPWM_Trapezoidal();
        current_mode = MODE_TRAPEZOIDAL;
        new_mode = MODE_TRAPEZOIDAL;
    }

    // Enable TBCLK
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;

    SyncCurrentMode();


    pwm_running = 1;
    GpioDataRegs.GPBSET.bit.GPIO36 = 1; // LED ON

    // Main loop: listen for UART commands
    while(1)
    {
        ProcessUART();
    }

    return 0;
}

//--------------------------------------------------------------
// UART command processing
//
// Strategy: v3-style wait for 5+ bytes in FIFO before parsing (robust
// at 4800bps). If the first byte is not the frame header 0xAA, keep
// consuming bytes from the FIFO until either 0xAA is found (and >=4
// bytes remain) or the FIFO drops below a full frame. This fixes v3's
// misalignment bug (which only consumed 1 byte and left 4 stale ones)
// without introducing the v5 busy-wait risk.
//--------------------------------------------------------------
void ProcessUART(void)
{
    Uint16 header, cmd, val_h, val_l, chk;
    Uint16 value;

    // Re-sync: drop bytes until the next would-be header is 0xAA and a
    // full frame (5 bytes including the header) is available.
    for (;;) {
        if (SciaRegs.SCIFFRX.bit.RXFFST < 5) {
            return; // not enough bytes for a full frame yet
        }
        header = SciaRegs.SCIRXBUF.all & 0xFF;
        if (header == FRAME_HEADER) {
            break;  // aligned; remaining 4 bytes are still in FIFO
        }
        // Otherwise: byte consumed, loop and try again with the next one.
    }

    cmd   = SciaRegs.SCIRXBUF.all & 0xFF;
    val_h = SciaRegs.SCIRXBUF.all & 0xFF;
    val_l = SciaRegs.SCIRXBUF.all & 0xFF;
    chk   = SciaRegs.SCIRXBUF.all & 0xFF;

    // Verify checksum
    if (chk != ((cmd ^ val_h ^ val_l) & 0xFF)) {
        scia_xmit(NAK);
        return;
    }

    value = (val_h << 8) | val_l;

    switch (cmd) {
        case CMD_SET_CARRIER:
            if (value >= 100 && value <= 5000) {
                new_carrier = value;
                scia_xmit(ACK);
            } else {
                scia_xmit(NAK);
            }
            break;

        case CMD_SET_CMP_L:
            new_cmp_l = value;
            scia_xmit(ACK);
            break;

        case CMD_SET_CMP_H:
            new_cmp_h = value;
            scia_xmit(ACK);
            break;

        case CMD_SET_DEADTIME:
            if (value >= 1 && value <= 10) {
                new_deadtime = value;
                scia_xmit(ACK);
            } else {
                scia_xmit(NAK);
            }
            break;

        case CMD_SET_MODE:
            if (value == MODE_TRAPEZOIDAL || value == MODE_TRIANGULAR) {
                new_mode = value;
                scia_xmit(ACK);
            } else {
                scia_xmit(NAK);
            }
            break;

        case CMD_APPLY:
            // Validate the pending parameter set against the requested mode.
            if (new_mode == MODE_TRIANGULAR) {
                if (new_cmp_l != new_cmp_h) {
                    scia_xmit(NAK);
                    break;
                }
            } else {
                if (new_cmp_l >= new_cmp_h) {
                    scia_xmit(NAK);
                    break;
                }
            }
            if (new_cmp_l > new_carrier || new_cmp_h > new_carrier) {
                scia_xmit(NAK);
                break;
            }
            carrier  = new_carrier;
            cmp_l    = new_cmp_l;
            cmp_h    = new_cmp_h;
            deadtime = new_deadtime;
            UpdateEPWM_Params();
            scia_xmit(ACK);
            break;

        case CMD_STOP_PWM:
            StopPWM();
            scia_xmit(ACK);
            break;

        case CMD_START_PWM:
            StartPWM();
            scia_xmit(ACK);
            break;

        default:
            scia_xmit(NAK);
            break;
    }
}

static void SyncCurrentMode(void)
{
    if (current_mode == MODE_TRIANGULAR) {
        EPwm4Regs.TBCTL.bit.SWFSYNC = 1;
    } else {
        EPwm1Regs.TBCTL.bit.SWFSYNC = 1;
    }
}

static void ReconfigureToTriangular(void)
{
    Uint16 was_running = pwm_running;

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;

    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO0 = 1;
    GpioDataRegs.GPACLEAR.bit.GPIO0 = 1;

    GpioCtrlRegs.GPAMUX1.bit.GPIO2 = 0;
    GpioCtrlRegs.GPADIR.bit.GPIO2 = 1;
    GpioDataRegs.GPACLEAR.bit.GPIO2 = 1;
    EDIS;

    ConfigureEPWM_Triangular();
    current_mode = MODE_TRIANGULAR;

    // Keep PWM stopped if it was already stopped before the mode switch.
    if (was_running) {
        EALLOW;
        CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
        EDIS;
        SyncCurrentMode();
    }
}

static void ReconfigureToTrapezoidal(void)
{
    Uint16 was_running = pwm_running;

    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    EDIS;

    ConfigureEPWM_Trapezoidal();
    current_mode = MODE_TRAPEZOIDAL;

    // Re-enable G0 EPWM outputs for trapezoidal mode.
    EALLOW;
    GpioCtrlRegs.GPAMUX1.bit.GPIO0 = 1;
    GpioCtrlRegs.GPAMUX1.bit.GPIO2 = 1;
    EDIS;

    // Keep PWM stopped if it was already stopped before the mode switch.
    if (was_running) {
        EALLOW;
        CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
        EDIS;
        SyncCurrentMode();
    }
}

static void ShadowUpdateTrapezoidal(void)
{
    EPwm1Regs.TBPRD = carrier;
    EPwm1Regs.CMPA.bit.CMPA = cmp_l;
    EPwm1Regs.CMPB.bit.CMPB = cmp_h;
    EPwm1Regs.DBRED = deadtime;
    EPwm1Regs.DBFED = deadtime;

    EPwm2Regs.TBPRD = carrier;
    EPwm2Regs.CMPA.bit.CMPA = cmp_l;
    EPwm2Regs.CMPB.bit.CMPB = cmp_h;
    EPwm2Regs.DBRED = deadtime;
    EPwm2Regs.DBFED = deadtime;

    EPwm4Regs.TBPRD = carrier;
    EPwm4Regs.CMPA.bit.CMPA = cmp_h;
    EPwm4Regs.DBRED = deadtime;
    EPwm4Regs.DBFED = deadtime;

    EPwm6Regs.TBPRD = carrier;
    EPwm6Regs.CMPA.bit.CMPA = cmp_l;
    EPwm6Regs.DBRED = deadtime;
    EPwm6Regs.DBFED = deadtime;
}

static void ShadowUpdateTriangular(void)
{
    EPwm4Regs.TBPRD = carrier;
    EPwm4Regs.CMPA.bit.CMPA = cmp_h;
    EPwm4Regs.DBRED = deadtime;
    EPwm4Regs.DBFED = deadtime;

    EPwm6Regs.TBPRD = carrier;
    EPwm6Regs.CMPA.bit.CMPA = cmp_l;
    EPwm6Regs.DBRED = deadtime;
    EPwm6Regs.DBFED = deadtime;
}



//--------------------------------------------------------------
// Update EPWM registers with current parameters
//--------------------------------------------------------------
void UpdateEPWM_Params(void)
{
    Uint16 requested_mode = new_mode;

    if (requested_mode != current_mode) {
        if (requested_mode == MODE_TRIANGULAR) {
            ReconfigureToTriangular();
        } else {
            ReconfigureToTrapezoidal();
        }
        return;
    }

    if (current_mode == MODE_TRIANGULAR) {
        ShadowUpdateTriangular();
    } else {
        ShadowUpdateTrapezoidal();
    }
}


void StopPWM(void)
{
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 0;
    EDIS;
    pwm_running = 0;
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1; // LED OFF
}

void StartPWM(void)
{
    EALLOW;
    CpuSysRegs.PCLKCR0.bit.TBCLKSYNC = 1;
    EDIS;
    SyncCurrentMode();
    pwm_running = 1;
    GpioDataRegs.GPBSET.bit.GPIO36 = 1; // LED ON
}

//--------------------------------------------------------------
// SCI-A functions
//--------------------------------------------------------------
void scia_init(void)
{
    SciaRegs.SCICCR.all  = 0x0007;  // 8-bit, no parity, 1 stop
    SciaRegs.SCICTL1.all = 0x0003;  // enable TX, RX
    SciaRegs.SCICTL2.all = 0x0003;
    SciaRegs.SCICTL2.bit.TXINTENA   = 1;
    SciaRegs.SCICTL2.bit.RXBKINTENA = 1;
    // 4800 baud @ LSPCLK=50MHz, BRR=1301
    SciaRegs.SCIHBAUD.all = 0x0005;
    SciaRegs.SCILBAUD.all = 0x0016;
    SciaRegs.SCICTL1.all  = 0x0023;  // release from reset
}

void scia_fifo_init(void)
{
    SciaRegs.SCIFFTX.all = 0xE040;
    SciaRegs.SCIFFRX.all = 0x2044;
    SciaRegs.SCIFFCT.all = 0x0;
}

void scia_xmit(int a)
{
    while (SciaRegs.SCIFFTX.bit.TXFFST != 0) {}
    SciaRegs.SCITXBUF.all = a;
}

//--------------------------------------------------------------
// EPWM configuration (same as your main.c)
//--------------------------------------------------------------
void ConfigureEPWM_Trapezoidal(void)
{
    // EPWM1A: G0 midpoint clamp (master)
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
    EPwm1Regs.CMPA.bit.CMPA = cmp_l;
    EPwm1Regs.CMPB.bit.CMPB = cmp_h;
    EPwm1Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm1Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm1Regs.AQCTLA.bit.CBU = AQ_CLEAR;
    EPwm1Regs.AQCTLA.bit.CBD = AQ_SET;
    EPwm1Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    EPwm1Regs.DBRED = deadtime;
    EPwm1Regs.DBFED = deadtime;
    EPwm1Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm1Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm1Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

    // EPWM2A: G0 redundant (slave)
    EPwm2Regs.TBCTR = 0;
    EPwm2Regs.TBPRD = carrier;
    EPwm2Regs.TBPHS.bit.TBPHS = 0;
    EPwm2Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm2Regs.TBCTL.bit.PHSEN    = TB_ENABLE;
    EPwm2Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm2Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm2Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm2Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;
    EPwm2Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm2Regs.CMPCTL.bit.SHDWBMODE = CC_SHADOW;
    EPwm2Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm2Regs.CMPCTL.bit.LOADBMODE = CC_CTR_ZERO;
    EPwm2Regs.CMPA.bit.CMPA = cmp_l;
    EPwm2Regs.CMPB.bit.CMPB = cmp_h;
    EPwm2Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm2Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm2Regs.AQCTLA.bit.CBU = AQ_CLEAR;
    EPwm2Regs.AQCTLA.bit.CBD = AQ_SET;
    EPwm2Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    EPwm2Regs.DBRED = deadtime;
    EPwm2Regs.DBFED = deadtime;
    EPwm2Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm2Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm2Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

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
    EPwm4Regs.CMPA.bit.CMPA = cmp_h;
    EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    EPwm4Regs.DBRED = deadtime;
    EPwm4Regs.DBFED = deadtime;
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm4Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm4Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

    // EPWM6B: GA upper arm S1 (via dead-band complement)
    EPwm6Regs.TBCTR = 0;
    EPwm6Regs.TBPRD = carrier;
    EPwm6Regs.TBPHS.bit.TBPHS = 0;
    EPwm6Regs.TBCTL.bit.CTRMODE = TB_COUNT_UPDOWN;
    EPwm6Regs.TBCTL.bit.PHSEN = TB_ENABLE;
    EPwm6Regs.TBCTL.bit.PRDLD = TB_SHADOW;
    EPwm6Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.CLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;
    EPwm6Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm6Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm6Regs.CMPA.bit.CMPA = cmp_l;
    EPwm6Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm6Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm6Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    EPwm6Regs.AQCTLA.bit.PRD = AQ_SET;
    EPwm6Regs.DBRED = deadtime;
    EPwm6Regs.DBFED = deadtime;
    EPwm6Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm6Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;
}

void ConfigureEPWM_Triangular(void)
{
    // EPWM4A: GB lower arm S3 (master in triangular mode)
    EPwm4Regs.TBCTR = 0;
    EPwm4Regs.TBPRD = carrier;
    EPwm4Regs.TBPHS.bit.TBPHS = 0;
    EPwm4Regs.TBCTL.bit.CTRMODE  = TB_COUNT_UPDOWN;
    EPwm4Regs.TBCTL.bit.PHSEN    = TB_DISABLE;
    EPwm4Regs.TBCTL.bit.PRDLD    = TB_SHADOW;
    EPwm4Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm4Regs.TBCTL.bit.CLKDIV   = TB_DIV1;
    EPwm4Regs.TBCTL.bit.SYNCOSEL = TB_CTR_ZERO;
    EPwm4Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm4Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm4Regs.CMPA.bit.CMPA = cmp_h;
    EPwm4Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm4Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm4Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    EPwm4Regs.DBRED = deadtime;
    EPwm4Regs.DBFED = deadtime;
    EPwm4Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm4Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm4Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;

    // EPWM6B: GA upper arm S1
    EPwm6Regs.TBCTR = 0;
    EPwm6Regs.TBPRD = carrier;
    EPwm6Regs.TBPHS.bit.TBPHS = 0;
    EPwm6Regs.TBCTL.bit.CTRMODE = TB_COUNT_UPDOWN;
    EPwm6Regs.TBCTL.bit.PHSEN = TB_ENABLE;
    EPwm6Regs.TBCTL.bit.PRDLD = TB_SHADOW;
    EPwm6Regs.TBCTL.bit.HSPCLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.CLKDIV = TB_DIV1;
    EPwm6Regs.TBCTL.bit.SYNCOSEL = TB_SYNC_IN;
    EPwm6Regs.CMPCTL.bit.SHDWAMODE = CC_SHADOW;
    EPwm6Regs.CMPCTL.bit.LOADAMODE = CC_CTR_ZERO;
    EPwm6Regs.CMPA.bit.CMPA = cmp_l;
    EPwm6Regs.AQCTLA.bit.CAU = AQ_SET;
    EPwm6Regs.AQCTLA.bit.CAD = AQ_CLEAR;
    EPwm6Regs.AQCTLA.bit.ZRO = AQ_CLEAR;
    EPwm6Regs.AQCTLA.bit.PRD = AQ_SET;
    EPwm6Regs.DBRED = deadtime;
    EPwm6Regs.DBFED = deadtime;
    EPwm6Regs.DBCTL.bit.IN_MODE = DBA_ALL;
    EPwm6Regs.DBCTL.bit.OUT_MODE = DB_FULL_ENABLE;
    EPwm6Regs.DBCTL.bit.POLSEL = DB_ACTV_HIC;
}

void SafetyCheck(void)
{
    if (cmp_l > cmp_h) {
        while(1) {
            GpioDataRegs.GPBTOGGLE.bit.GPIO36 = 1;
            DELAY_US(500000);
        }
    }
    GpioDataRegs.GPBSET.bit.GPIO36 = 1;
    DELAY_US(500000);
    GpioDataRegs.GPBCLEAR.bit.GPIO36 = 1;
}
