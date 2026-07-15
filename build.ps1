# Сборка проекта в один .exe (PyInstaller), с внутренним Tesseract-OCR —
# пользователю не нужно ничего доустанавливать отдельно.
#
# Запуск: из корня проекта в PowerShell:
#   .\build.ps1
#
# Результат: dist\GTA5RPUtil.exe (один файл).

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Не найден .venv\Scripts\python.exe. Создайте виртуальное окружение и установите requirements.txt."
}

if (-not (Test-Path (Join-Path $root "tesseract_bin\tesseract.exe"))) {
    throw "Не найдена папка tesseract_bin\ с встроенным Tesseract-OCR. " +
          "Скопируйте туда tesseract.exe, все *.dll и tessdata\ (eng, rus, osd) " +
          "из установленного Tesseract-OCR (обычно C:\Program Files\Tesseract-OCR)."
}

Write-Host "Проверяю/устанавливаю PyInstaller..." -ForegroundColor Cyan
& $venvPython -m pip install --quiet --upgrade pyinstaller

Write-Host "Очищаю предыдущую сборку..." -ForegroundColor Cyan
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\build"
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue "$root\dist"
Remove-Item -Force -ErrorAction SilentlyContinue "$root\GTA5RPUtil.spec"

Write-Host "Собираю exe (это может занять несколько минут — PySide6 большой)..." -ForegroundColor Cyan
& $venvPython -m PyInstaller `
    --name "GTA5RPUtil-v.1.0" `
    --onefile `
    --windowed `
    --icon "logo.ico" `
    --add-data "templates;templates" `
    --add-data "tesseract_bin;tesseract_bin" `
    --add-data "logo.jpg;." `
    --collect-submodules pytesseract `
    --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtQuick `
    --exclude-module PySide6.QtQuick3D `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtMultimedia `
    --exclude-module PySide6.QtNetwork `
    --exclude-module PySide6.QtBluetooth `
    --exclude-module PySide6.QtPositioning `
    --exclude-module PySide6.QtSensors `
    --exclude-module PySide6.QtSql `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtCharts `
    --exclude-module PySide6.QtDesigner `
    --exclude-module PySide6.QtHelp `
    --exclude-module PySide6.QtLocation `
    --exclude-module PySide6.QtNfc `
    main.py

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller завершился с ошибкой (код $LASTEXITCODE)."
}

Write-Host ""
Write-Host "Готово: dist\GTA5RPUtil.exe" -ForegroundColor Green
Write-Host "Скопируйте рядом с exe файл input.txt (или укажите свой путь в GUI)." -ForegroundColor Green
