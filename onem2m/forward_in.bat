@echo off
rem WSL 안의 IN-CSE(3000)를 노트북 외부로 포워딩. 관리자 권한으로 실행 (우클릭 - 관리자 권한으로 실행)
rem WSL IP는 재부팅마다 바뀔 수 있어 매번 자동 감지한다.
for /f "tokens=1" %%i in ('wsl -d Ubuntu-22.04 hostname -I') do set WSLIP=%%i
echo WSL IP = %WSLIP%
netsh interface portproxy reset
netsh interface portproxy add v4tov4 listenport=3000 listenaddress=0.0.0.0 connectport=3000 connectaddress=%WSLIP%
netsh advfirewall firewall add rule name="tinyIoT3000" dir=in action=allow protocol=TCP localport=3000 >nul 2>&1
netsh interface portproxy show all
pause
