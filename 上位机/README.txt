运行主程序：
python integrated_auto_sweep_measure_autosetup_2s_firstwait.py

本版本修复：
1. 第二页电流源控制增加“断开连接”按钮。
2. 断开前自动发送 OUTP OFF，释放当前连接的串口/VISA 资源。
3. 重新连接前会先释放旧连接，减少 VI_ERROR_RSRC_BUSY。
4. 保留直流偏置扫描逻辑和示波器 Auto 等待修正。
