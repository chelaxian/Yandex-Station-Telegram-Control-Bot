' VBScript launcher to bypass broken .bat/.cmd file associations
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = currentDir
WshShell.Run "cmd.exe /k """ & currentDir & "\start.bat""", 1, False
