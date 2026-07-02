; Скрипт сборки установщика Inno Setup для Job Hunter AI
; Настроен на работу с относительными путями (полная свобода перемещения папок!)

#define MyAppName "Job Hunter AI"
#define MyAppVersion "3.1"
#define MyAppPublisher "Job Hunter"
#define MyAppExeName "Job Hunter AI.exe"
; Используем точку ".", чтобы пути искались относительно папки со скриптом
#define MyProjectDir "."

[Setup]
AppId={{8A87C1D1-A9D4-4DB4-A59B-51475A9C0783}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes

; Лицензионное соглашение с галочкой
LicenseFile={#MyProjectDir}\license.txt

; Иконка самого файла установки (инсталлятора)
SetupIconFile={#MyProjectDir}\icon.ico
; Сохраняем готовый файл установщика прямо в текущую папку проекта
OutputDir={#MyProjectDir}
OutputBaseFilename=JobHunterAI_Setup
Compression=lzma2/ultra
SolidCompression=yes
WizardStyle=modern

; Показываем диалог выбора языка установщика
ShowLanguageDialog=yes
; English первый в списке = дефолт; отключаем автоподбор по локали системы
LanguageDetectionMethod=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
; Создать ярлык на Рабочем столе
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
; 1. Главный исполняемый файл приложения
Source: "{#MyProjectDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; 2. Обязательная системная папка зависимостей _internal, созданная PyInstaller
Source: "{#MyProjectDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; 3. Файл иконки программы для ярлыков
Source: "{#MyProjectDir}\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; 4. Файл лицензионного соглашения
Source: "{#MyProjectDir}\license.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Ярлык программы в меню Пуск
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
; Ярлык удаления программы
Name: "{group}\Удалить Job Hunter AI"; Filename: "{uninstallexe}"
; Ярлык на Рабочем столе
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; Запуск приложения сразу после успешной установки (галочка по умолчанию активна)
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Полная очистка папки приложения при удалении (включая создаваемые config.json и логи)
Type: filesandordirs; Name: "{app}"
