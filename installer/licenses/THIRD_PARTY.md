# Third-party notices for the preview

The preview uses PySide6 Essentials / Qt 6.8.3 and Shiboken6 under the LGPL-3.0-only option (among other available licence options). The application is an independent work; Qt libraries are provided as separate dynamically linked files in the `_internal` directory. The included `LGPL-3.0-only.txt` and `GPL-3.0-only.txt` contain the relevant licence texts. You may replace compatible Qt libraries, subject to the LGPL. Source for the corresponding unmodified components is available from:

- PySide6 and Shiboken6 6.8.3: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.8.3
- Qt 6.8.3: https://download.qt.io/official_releases/qt/6.8/6.8.3/submodules/

Other Python runtime and package license notices are collected alongside this file from the installed distributions at build time. PyInstaller's bootloader exception permits distribution of the resulting executable; its licence is included in the package. See `NOTICE.md` for upstream design credits.

For offline wake-word spotting this build bundles the Vosk toolkit (Apache License 2.0, https://github.com/alphacep/vosk-api) and the `vosk-model-small-en-us-0.15` English model (Apache License 2.0, https://alphacephei.com/vosk/models), used only on this device to detect the "Hi Vox" wake phrase. No Groq models or voices are bundled; Groq processes requests online.

The sounddevice package (MIT) includes a PortAudio dynamic library (MIT). The PortAudio license is in `PORTAUDIO-LICENSE.txt`; the build removes ASIO, 32-bit and ARM variants from this x64 installer. Groq processes requests online.
