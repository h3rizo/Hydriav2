Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
appDir = fso.GetParentFolderName(WScript.ScriptFullName)
electronExe = fso.BuildPath(fso.GetParentFolderName(appDir), "WeatherWidgetElectron\node_modules\electron\dist\electron.exe")
If fso.FileExists(electronExe) Then
    shell.CurrentDirectory = appDir
    shell.Run """" & electronExe & """ """ & appDir & """", 0, False
Else
    MsgBox "Electron introuvable dans WeatherWidgetElectron.", 48, "Hydria"
End If
