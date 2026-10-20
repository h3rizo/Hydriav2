' Lance le widget meteo Electron sans fenetre console visible.
' Utilise pour le demarrage automatique de Windows.

Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
electronExe = scriptDir & "\node_modules\electron\dist\electron.exe"
appDir = scriptDir

If fso.FileExists(electronExe) Then
    shell.CurrentDirectory = scriptDir
    shell.Run """" & electronExe & """ """ & appDir & """", 0, False
Else
    MsgBox "Electron introuvable. Lancez d'abord 'Lancer Widget Meteo.bat' manuellement une fois.", 48, "Widget Meteo"
End If
