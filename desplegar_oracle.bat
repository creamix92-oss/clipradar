@echo off
REM Doble clic: sube ClipRadar a la VM de Oracle y lo deja corriendo en el puerto 8787.
setlocal
set IP=129.159.110.35
set USR=opc
set SRCKEY=%~dp0_oracle_ssh\clipradar_key
set KEYDIR=%USERPROFILE%\.ssh
set KEY=%KEYDIR%\clipradar_oracle_key
set SSHO=-i "%KEY%" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=30 -o IdentitiesOnly=yes

echo [1/4] Preparando la llave segura...
if not exist "%KEYDIR%" mkdir "%KEYDIR%"
copy /Y "%SRCKEY%" "%KEY%" >nul
if errorlevel 1 goto :fail
icacls "%KEY%" /reset >nul
icacls "%KEY%" /inheritance:r >nul
icacls "%KEY%" /grant:r "%USERNAME%:R" >nul
if errorlevel 1 goto :fail

echo [2/4] Empaquetando ClipRadar...
tar -czf "%TEMP%\clipradar.tgz" --exclude=_oracle_ssh --exclude=data --exclude=.git --exclude=__pycache__ --exclude=cloudflared.exe --exclude=web.bak-antes-de-modernizar -C "%~dp0." .
if errorlevel 1 goto :fail

echo [3/4] Subiendo a Oracle (%IP%)...
scp %SSHO% "%TEMP%\clipradar.tgz" "%~dp0oracle_remote_setup.sh" %USR%@%IP%:~/
if errorlevel 1 goto :fail

echo [4/4] Instalando y arrancando (tarda varios minutos, no cierres esta ventana)...
ssh %SSHO% %USR%@%IP% "sed -i 's/\r$//' ~/oracle_remote_setup.sh && bash ~/oracle_remote_setup.sh"
if errorlevel 1 goto :fail

echo.
echo LISTO. Abre: http://%IP%:8787
pause
exit /b 0
:fail
echo.
echo ERROR. Copia lo que dice arriba y mandamelo.
pause
exit /b 1
