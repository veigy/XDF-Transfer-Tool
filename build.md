# Build Instructions for XDF Transfer Tool

To create a single all-in-one EXE file that contains everything required and has its own icon, follow these steps.

## 1. Install PyInstaller
If you don't have it yet, install it via terminal:
```powershell
pip install pyinstaller
```

## 2. Command to generate EXE
Run this command in the root folder of the project (`XDF-Transfer-Tool`):

```powershell
pyinstaller --onefile --noconsole --icon=favicon.ico --add-data "favicon.ico;." --name "XDF-Transfer-Tool" main.py
```

### Parameters:
- `--onefile`: Packages everything into a single .exe file.
- `--noconsole`: Prevents a black terminal window from opening when launching (clean GUI).
- `--icon=favicon.ico`: Sets the icon for the .exe file in Windows.
- `--add-data "favicon.ico;."`: Bundles the icon inside the archive so the application can load it at runtime (for the window corner icon).
- `--name "XDF-Transfer-Tool"`: The name of the resulting file.

## 3. Where to find the result?
Once finished (it may take a minute), a `dist` folder will be created containing your final `XDF-Transfer-Tool.exe` file.
