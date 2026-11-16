# Сторонние компоненты

Программа использует сторонние библиотеки и модели. Их лицензии и авторские права сохраняются за соответствующими правообладателями; лицензии разных компонентов не заменяют друг друга.

| Компонент | Назначение | Исходники и сведения |
| --- | --- | --- |
| PySide6 / Qt | Интерфейс Windows | [Qt for Python](https://www.qt.io/qt-for-python), [лицензирование Qt](https://www.qt.io/licensing/) |
| faster-whisper | CPU/NVIDIA-распознавание | [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| CTranslate2 | Вычисления | [OpenNMT/CTranslate2](https://github.com/OpenNMT/CTranslate2) |
| Whisper / модели | Распознавание речи | [openai/whisper](https://github.com/openai/whisper), [GGML-модели](https://huggingface.co/ggerganov/whisper.cpp) |
| whisper.cpp | Vulkan-распознавание | [ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) |
| Whisper.net 1.8.1 | Обвязка и нативные Vulkan/NoAvx-библиотеки | [sandrohanea/whisper.net](https://github.com/sandrohanea/whisper.net), [NuGet](https://www.nuget.org/packages/Whisper.net/1.8.1) |
| .NET | Автономная среда GPU-компонента | [dotnet/runtime](https://github.com/dotnet/runtime) |
| PyAV / FFmpeg | Чтение аудио и видео | [PyAV](https://github.com/PyAV-Org/PyAV), [FFmpeg](https://ffmpeg.org/), [условия FFmpeg](https://ffmpeg.org/legal.html) |
| ONNX Runtime / Silero VAD | Обнаружение речи | [ONNX Runtime](https://github.com/microsoft/onnxruntime), [Silero VAD](https://github.com/snakers4/silero-vad) |
| python-docx / lxml | Документы Word | [python-docx](https://github.com/python-openxml/python-docx), [lxml](https://github.com/lxml/lxml) |
| NumPy | Аудиобуферы | [numpy/numpy](https://github.com/numpy/numpy) |
| Hugging Face Hub / tokenizers | Загрузка и токенизация | [huggingface_hub](https://github.com/huggingface/huggingface_hub), [tokenizers](https://github.com/huggingface/tokenizers) |
| PyInstaller | Упаковка Windows-программы | [PyInstaller](https://github.com/pyinstaller/pyinstaller) |

В архиве сохраняются лицензии, включённые в библиотеки. Дополнительные доступные тексты лицензий установленных Python-пакетов собираются в `licenses/python-packages`. У автономного .NET-компонента сохраняются `LICENSE.txt`, `ThirdPartyNotices.txt` и `WHISPER-NET-LICENSE.txt`, когда они поставляются сборкой.

Набор и условия медиакодеков зависят от сборки FFmpeg в PyAV; ориентируйтесь на уведомления соответствующего пакета и его исходники. Модели сохраняют условия исходных проектов.
