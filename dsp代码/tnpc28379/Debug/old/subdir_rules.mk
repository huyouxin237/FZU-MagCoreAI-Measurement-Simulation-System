################################################################################
# Automatically-generated file. Do not edit!
################################################################################

SHELL = cmd.exe

# Each subdirectory must supply rules for building sources it contributes
old/%.obj: ../old/%.c $(GEN_OPTS) | $(GEN_FILES) $(GEN_MISC_FILES)
	@echo 'Building file: "$<"'
	@echo 'Invoking: C2000 Compiler'
	"C:/ti/ccs1250/ccs/tools/compiler/ti-cgt-c2000_22.6.1.LTS/bin/cl2000" -v28 -ml -mt --cla_support=cla1 --float_support=fpu32 --tmu_support=tmu0 --vcu_support=vcu2 --include_path="C:/ti/ccs1250/ccs/tools/compiler/ti-cgt-c2000_22.6.1.LTS/include" --include_path="D:/ccsproject/tnpc28379/F2837xD_common/driverlib" --include_path="D:/ccsproject/tnpc28379/F2837xD_common/inc" --include_path="D:/ccsproject/tnpc28379/F2837xD_common/include" --include_path="D:/ccsproject/tnpc28379/F2837xD_headers/include" --advice:performance=all --define=CPU1 -g --diag_warning=225 --diag_wrap=off --display_error_number --abi=coffabi --preproc_with_compile --preproc_dependency="old/$(basename $(<F)).d_raw" --obj_directory="old" $(GEN_OPTS__FLAG) "$<"
	@echo 'Finished building: "$<"'
	@echo ' '


