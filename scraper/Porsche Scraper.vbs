Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get the directory where this script is located
scriptPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Change to the script directory
WshShell.CurrentDirectory = scriptPath

' Check for venv in parent directory (project root)
parentDir = fso.GetParentFolderName(scriptPath)
venvPython = parentDir & "\venv\Scripts\python.exe"

' Use venv Python if it exists, otherwise use system Python
If fso.FileExists(venvPython) Then
    pythonCmd = """" & venvPython & """ gui_app.py"
Else
    pythonCmd = "python gui_app.py"
End If

' Run Python script without showing console window
WshShell.Run pythonCmd, 0, False

Set WshShell = Nothing
Set fso = Nothing

