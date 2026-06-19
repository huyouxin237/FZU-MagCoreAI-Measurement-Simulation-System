################################################################################
# Automatically-generated file. Do not edit!
################################################################################

SHELL = cmd.exe

# Add inputs and outputs from these tool invocations to the build variables 
ASM_SRCS += \
../F2837xD_common/source/F2837xD_CodeStartBranch.asm 

C_SRCS += \
../F2837xD_common/source/F2837xD_Adc.c \
../F2837xD_common/source/F2837xD_CpuTimers.c \
../F2837xD_common/source/F2837xD_DefaultISR.c \
../F2837xD_common/source/F2837xD_Dma.c \
../F2837xD_common/source/F2837xD_ECap.c \
../F2837xD_common/source/F2837xD_EPwm.c \
../F2837xD_common/source/F2837xD_EQep.c \
../F2837xD_common/source/F2837xD_Gpio.c \
../F2837xD_common/source/F2837xD_I2C.c \
../F2837xD_common/source/F2837xD_Ipc.c \
../F2837xD_common/source/F2837xD_Ipc_Driver.c \
../F2837xD_common/source/F2837xD_Ipc_Driver_Lite.c \
../F2837xD_common/source/F2837xD_Ipc_Driver_Util.c \
../F2837xD_common/source/F2837xD_Mcbsp.c \
../F2837xD_common/source/F2837xD_Pbist.c \
../F2837xD_common/source/F2837xD_PieCtrl.c \
../F2837xD_common/source/F2837xD_PieVect.c \
../F2837xD_common/source/F2837xD_Sci.c \
../F2837xD_common/source/F2837xD_Spi.c \
../F2837xD_common/source/F2837xD_SysCtrl.c \
../F2837xD_common/source/F2837xD_Upp.c \
../F2837xD_common/source/F2837xD_sci_io.c \
../F2837xD_common/source/F2837xD_sdfm_drivers.c \
../F2837xD_common/source/F2837xD_struct.c 

C_DEPS += \
./F2837xD_common/source/F2837xD_Adc.d \
./F2837xD_common/source/F2837xD_CpuTimers.d \
./F2837xD_common/source/F2837xD_DefaultISR.d \
./F2837xD_common/source/F2837xD_Dma.d \
./F2837xD_common/source/F2837xD_ECap.d \
./F2837xD_common/source/F2837xD_EPwm.d \
./F2837xD_common/source/F2837xD_EQep.d \
./F2837xD_common/source/F2837xD_Gpio.d \
./F2837xD_common/source/F2837xD_I2C.d \
./F2837xD_common/source/F2837xD_Ipc.d \
./F2837xD_common/source/F2837xD_Ipc_Driver.d \
./F2837xD_common/source/F2837xD_Ipc_Driver_Lite.d \
./F2837xD_common/source/F2837xD_Ipc_Driver_Util.d \
./F2837xD_common/source/F2837xD_Mcbsp.d \
./F2837xD_common/source/F2837xD_Pbist.d \
./F2837xD_common/source/F2837xD_PieCtrl.d \
./F2837xD_common/source/F2837xD_PieVect.d \
./F2837xD_common/source/F2837xD_Sci.d \
./F2837xD_common/source/F2837xD_Spi.d \
./F2837xD_common/source/F2837xD_SysCtrl.d \
./F2837xD_common/source/F2837xD_Upp.d \
./F2837xD_common/source/F2837xD_sci_io.d \
./F2837xD_common/source/F2837xD_sdfm_drivers.d \
./F2837xD_common/source/F2837xD_struct.d 

OBJS += \
./F2837xD_common/source/F2837xD_Adc.obj \
./F2837xD_common/source/F2837xD_CodeStartBranch.obj \
./F2837xD_common/source/F2837xD_CpuTimers.obj \
./F2837xD_common/source/F2837xD_DefaultISR.obj \
./F2837xD_common/source/F2837xD_Dma.obj \
./F2837xD_common/source/F2837xD_ECap.obj \
./F2837xD_common/source/F2837xD_EPwm.obj \
./F2837xD_common/source/F2837xD_EQep.obj \
./F2837xD_common/source/F2837xD_Gpio.obj \
./F2837xD_common/source/F2837xD_I2C.obj \
./F2837xD_common/source/F2837xD_Ipc.obj \
./F2837xD_common/source/F2837xD_Ipc_Driver.obj \
./F2837xD_common/source/F2837xD_Ipc_Driver_Lite.obj \
./F2837xD_common/source/F2837xD_Ipc_Driver_Util.obj \
./F2837xD_common/source/F2837xD_Mcbsp.obj \
./F2837xD_common/source/F2837xD_Pbist.obj \
./F2837xD_common/source/F2837xD_PieCtrl.obj \
./F2837xD_common/source/F2837xD_PieVect.obj \
./F2837xD_common/source/F2837xD_Sci.obj \
./F2837xD_common/source/F2837xD_Spi.obj \
./F2837xD_common/source/F2837xD_SysCtrl.obj \
./F2837xD_common/source/F2837xD_Upp.obj \
./F2837xD_common/source/F2837xD_sci_io.obj \
./F2837xD_common/source/F2837xD_sdfm_drivers.obj \
./F2837xD_common/source/F2837xD_struct.obj 

ASM_DEPS += \
./F2837xD_common/source/F2837xD_CodeStartBranch.d 

OBJS__QUOTED += \
"F2837xD_common\source\F2837xD_Adc.obj" \
"F2837xD_common\source\F2837xD_CodeStartBranch.obj" \
"F2837xD_common\source\F2837xD_CpuTimers.obj" \
"F2837xD_common\source\F2837xD_DefaultISR.obj" \
"F2837xD_common\source\F2837xD_Dma.obj" \
"F2837xD_common\source\F2837xD_ECap.obj" \
"F2837xD_common\source\F2837xD_EPwm.obj" \
"F2837xD_common\source\F2837xD_EQep.obj" \
"F2837xD_common\source\F2837xD_Gpio.obj" \
"F2837xD_common\source\F2837xD_I2C.obj" \
"F2837xD_common\source\F2837xD_Ipc.obj" \
"F2837xD_common\source\F2837xD_Ipc_Driver.obj" \
"F2837xD_common\source\F2837xD_Ipc_Driver_Lite.obj" \
"F2837xD_common\source\F2837xD_Ipc_Driver_Util.obj" \
"F2837xD_common\source\F2837xD_Mcbsp.obj" \
"F2837xD_common\source\F2837xD_Pbist.obj" \
"F2837xD_common\source\F2837xD_PieCtrl.obj" \
"F2837xD_common\source\F2837xD_PieVect.obj" \
"F2837xD_common\source\F2837xD_Sci.obj" \
"F2837xD_common\source\F2837xD_Spi.obj" \
"F2837xD_common\source\F2837xD_SysCtrl.obj" \
"F2837xD_common\source\F2837xD_Upp.obj" \
"F2837xD_common\source\F2837xD_sci_io.obj" \
"F2837xD_common\source\F2837xD_sdfm_drivers.obj" \
"F2837xD_common\source\F2837xD_struct.obj" 

C_DEPS__QUOTED += \
"F2837xD_common\source\F2837xD_Adc.d" \
"F2837xD_common\source\F2837xD_CpuTimers.d" \
"F2837xD_common\source\F2837xD_DefaultISR.d" \
"F2837xD_common\source\F2837xD_Dma.d" \
"F2837xD_common\source\F2837xD_ECap.d" \
"F2837xD_common\source\F2837xD_EPwm.d" \
"F2837xD_common\source\F2837xD_EQep.d" \
"F2837xD_common\source\F2837xD_Gpio.d" \
"F2837xD_common\source\F2837xD_I2C.d" \
"F2837xD_common\source\F2837xD_Ipc.d" \
"F2837xD_common\source\F2837xD_Ipc_Driver.d" \
"F2837xD_common\source\F2837xD_Ipc_Driver_Lite.d" \
"F2837xD_common\source\F2837xD_Ipc_Driver_Util.d" \
"F2837xD_common\source\F2837xD_Mcbsp.d" \
"F2837xD_common\source\F2837xD_Pbist.d" \
"F2837xD_common\source\F2837xD_PieCtrl.d" \
"F2837xD_common\source\F2837xD_PieVect.d" \
"F2837xD_common\source\F2837xD_Sci.d" \
"F2837xD_common\source\F2837xD_Spi.d" \
"F2837xD_common\source\F2837xD_SysCtrl.d" \
"F2837xD_common\source\F2837xD_Upp.d" \
"F2837xD_common\source\F2837xD_sci_io.d" \
"F2837xD_common\source\F2837xD_sdfm_drivers.d" \
"F2837xD_common\source\F2837xD_struct.d" 

ASM_DEPS__QUOTED += \
"F2837xD_common\source\F2837xD_CodeStartBranch.d" 

C_SRCS__QUOTED += \
"../F2837xD_common/source/F2837xD_Adc.c" \
"../F2837xD_common/source/F2837xD_CpuTimers.c" \
"../F2837xD_common/source/F2837xD_DefaultISR.c" \
"../F2837xD_common/source/F2837xD_Dma.c" \
"../F2837xD_common/source/F2837xD_ECap.c" \
"../F2837xD_common/source/F2837xD_EPwm.c" \
"../F2837xD_common/source/F2837xD_EQep.c" \
"../F2837xD_common/source/F2837xD_Gpio.c" \
"../F2837xD_common/source/F2837xD_I2C.c" \
"../F2837xD_common/source/F2837xD_Ipc.c" \
"../F2837xD_common/source/F2837xD_Ipc_Driver.c" \
"../F2837xD_common/source/F2837xD_Ipc_Driver_Lite.c" \
"../F2837xD_common/source/F2837xD_Ipc_Driver_Util.c" \
"../F2837xD_common/source/F2837xD_Mcbsp.c" \
"../F2837xD_common/source/F2837xD_Pbist.c" \
"../F2837xD_common/source/F2837xD_PieCtrl.c" \
"../F2837xD_common/source/F2837xD_PieVect.c" \
"../F2837xD_common/source/F2837xD_Sci.c" \
"../F2837xD_common/source/F2837xD_Spi.c" \
"../F2837xD_common/source/F2837xD_SysCtrl.c" \
"../F2837xD_common/source/F2837xD_Upp.c" \
"../F2837xD_common/source/F2837xD_sci_io.c" \
"../F2837xD_common/source/F2837xD_sdfm_drivers.c" \
"../F2837xD_common/source/F2837xD_struct.c" 

ASM_SRCS__QUOTED += \
"../F2837xD_common/source/F2837xD_CodeStartBranch.asm" 


