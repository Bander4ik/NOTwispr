# 🎤 NOTwispr

> **A free, local alternative to Wispr Flow** — AI-powered voice dictation for Windows using the Deepgram Nova-3 engine.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)](https://python.org)
[![Deepgram](https://img.shields.io/badge/Deepgram-Nova--3-purple)](https://deepgram.com)
[![Platform](https://img.shields.io/badge/Platform-Windows-0078D4?logo=windows)](https://www.microsoft.com/windows)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![macOS](https://img.shields.io/badge/macOS-Guide-silver?logo=apple)](README_MAC.md)

> 🍎 **macOS users:** see the [macOS Installation Guide](README_MAC.md) for platform-specific setup steps.

---

## 🇬🇧 English

### What is NOTwispr?

NOTwispr lets you dictate text **into any application** on Windows — browsers, editors, messengers, IDEs — just like Wispr Flow, but **100% free and open source**. It uses the Deepgram **Nova-3** speech-to-text API over WebSocket for real-time, low-latency transcription.

**Default language: Ukrainian.** You can change it to any language supported by Deepgram.

### ✨ Features

- 🎙️ **Global hotkey** — `Left Alt + Q` to start and stop recording from any window
- ⚡ **Real-time streaming** — audio is sent to Deepgram over WebSocket while you speak
- 📋 **Instant paste** — transcribed text is pasted directly into the focused field via `Ctrl+V`
- 🧠 **Deepgram Nova-3** — one of the most accurate speech recognition models available
- 🔒 **Privacy-first** — no local data storage, audio is only sent to Deepgram during recording
- 💸 **Low cost** — Deepgram offers $200 free credit on signup (enough for ~thousands of hours)

### 📋 Requirements

| Requirement | Version / Notes |
|---|---|
| **OS** | Windows 10/11 |
| **Python** | 3.11 or higher |
| **Microphone** | Any working input device |
| **Internet** | Required (for Deepgram API) |
| **Deepgram API Key** | Free at [console.deepgram.com](https://console.deepgram.com/) |

### 🚀 Installation

#### Step 1 — Clone the repository

```bash
git clone https://github.com/Bander4ik/NOTwispr.git
cd NOTwispr
```

#### Step 2 — Create and activate a virtual environment (recommended)

```bash
python -m venv venv
venv\Scripts\activate
```

#### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ **PyAudio note:** If `pip install pyaudio` fails, install it manually:
> ```bash
> pip install pipwin
> pipwin install pyaudio
> ```
> Alternatively, download the wheel from [Unofficial Windows Binaries](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) and run `pip install <downloaded_file>.whl`.

#### Step 4 — Get your Deepgram API Key

1. Sign up at [console.deepgram.com](https://console.deepgram.com/)
2. Create a new API key (you get **$200 free credit**)
3. Copy the key

#### Step 5 — Configure the environment

```bash
copy .env.example .env
```

Open `.env` and paste your API key:

```env
DEEPGRAM_API_KEY=your_actual_api_key_here
```

#### Step 6 — Run

```bash
python notwispr.py
```

Or double-click **`start.bat`** for one-click launch.

### 🎮 Usage

| Action | Shortcut |
|---|---|
| **Start recording** | `Left Alt + Q` |
| **Stop recording & paste text** | `Left Alt + Q` (again) |
| **Exit the program** | `Ctrl+C` in terminal |

1. Make sure the cursor is in the text field where you want the text to appear
2. Press `Left Alt + Q` — recording starts (you'll see `🎙️ Запис...` in the terminal)
3. Speak naturally
4. Press `Left Alt + Q` again — recording stops, text is transcribed and pasted automatically

### ⚙️ Configuration

You can tweak the following constants at the top of `notwispr.py`:

| Constant | Default | Description |
|---|---|---|
| `HOTKEY_ALT` | `True` | Require Alt key |
| `HOTKEY_WIN` | `False` | Require Win key |
| `HOTKEY_CHAR` | `'q'` | The trigger character |
| `AUDIO_RATE` | `16000` | Sample rate (Hz) |
| `DEBUG_MODE` | `True` | Print debug info to terminal |

To change the transcription language, edit the `language` parameter in `DeepgramTranscriber.start()`:

```python
language="uk",  # Ukrainian — change to "en", "de", "fr", etc.
```

### 🏗️ Architecture

```
NOTwispr
├── AudioRecorder       — captures microphone audio (PyAudio, PCM 16-bit 16kHz)
├── DeepgramTranscriber — streams audio via WebSocket to Deepgram Nova-3
├── TextInjector        — pastes result into active window (Ctrl+V / fallback char-by-char)
└── HotkeyManager       — global keyboard listener (pynput), toggle on Alt+Q
```

### 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| `DEEPGRAM_API_KEY not found` | Create `.env` from `.env.example` and add your key |
| `PyAudio install fails` | Use `pipwin install pyaudio` or download the wheel manually |
| `Hotkey doesn't work` | Run as Administrator or check if another app is capturing the same shortcut |
| `Text not pasting` | Make sure the target field is focused/active before pressing the hotkey |
| `Empty transcription` | Speak louder/closer to mic; check mic is not muted in Windows settings |

---

## 🇺🇦 Українська

### Що таке NOTwispr?

NOTwispr дозволяє диктувати текст **у будь-яку програму** на Windows — браузери, редактори, месенджери, IDE — так само як Wispr Flow, але **безкоштовно та з відкритим кодом**. Використовує API Deepgram **Nova-3** через WebSocket для транскрибування в реальному часі.

**Мова за замовчуванням: Українська.** Можна змінити на будь-яку мову, що підтримується Deepgram.

### ✨ Можливості

- 🎙️ **Глобальний хоткей** — `Left Alt + Q` для старту і зупинки запису з будь-якого вікна
- ⚡ **Стрімінг у реальному часі** — аудіо передається до Deepgram через WebSocket під час мовлення
- 📋 **Миттєва вставка** — транскрибований текст вставляється в активне поле через `Ctrl+V`
- 🧠 **Deepgram Nova-3** — одна з найточніших моделей розпізнавання мови
- 🔒 **Приватність** — немає локального зберігання даних; аудіо надсилається до Deepgram лише під час запису
- 💸 **Низька вартість** — Deepgram дає $200 безкоштовного кредиту під час реєстрації

### 📋 Вимоги

| Вимога | Версія / Примітки |
|---|---|
| **ОС** | Windows 10/11 |
| **Python** | 3.11 або вище |
| **Мікрофон** | Будь-який робочий пристрій введення |
| **Інтернет** | Необхідний (для API Deepgram) |
| **Deepgram API Key** | Безкоштовно на [console.deepgram.com](https://console.deepgram.com/) |

### 🚀 Встановлення

#### Крок 1 — Клонування репозиторію

```bash
git clone https://github.com/Bander4ik/NOTwispr.git
cd NOTwispr
```

#### Крок 2 — Створення та активація віртуального середовища (рекомендовано)

```bash
python -m venv venv
venv\Scripts\activate
```

#### Крок 3 — Встановлення залежностей

```bash
pip install -r requirements.txt
```

> ⚠️ **Проблема з PyAudio:** Якщо `pip install pyaudio` не спрацьовує, встановіть вручну:
> ```bash
> pip install pipwin
> pipwin install pyaudio
> ```
> Або завантажте wheel з [Unofficial Windows Binaries](https://www.lfd.uci.edu/~gohlke/pythonlibs/#pyaudio) і виконайте `pip install <файл>.whl`.

#### Крок 4 — Отримання Deepgram API Key

1. Зареєструйтесь на [console.deepgram.com](https://console.deepgram.com/)
2. Створіть новий API ключ (отримаєте **$200 безкоштовного кредиту**)
3. Скопіюйте ключ

#### Крок 5 — Налаштування середовища

```bash
copy .env.example .env
```

Відкрийте `.env` і вставте ваш ключ:

```env
DEEPGRAM_API_KEY=ваш_api_ключ_тут
```

#### Крок 6 — Запуск

```bash
python notwispr.py
```

Або двічі клікніть **`start.bat`** для запуску в один клік.

### 🎮 Використання

| Дія | Комбінація |
|---|---|
| **Почати запис** | `Left Alt + Q` |
| **Зупинити запис і вставити текст** | `Left Alt + Q` (ще раз) |
| **Вийти з програми** | `Ctrl+C` у терміналі |

1. Переконайтеся, що курсор знаходиться в текстовому полі, куди має з'явитися текст
2. Натисніть `Left Alt + Q` — запис починається (у терміналі з'явиться `🎙️ Запис...`)
3. Говоріть природньо
4. Натисніть `Left Alt + Q` ще раз — запис зупиняється, текст транскрибується і автоматично вставляється

### ⚙️ Налаштування

Можна змінити наступні константи на початку `notwispr.py`:

| Константа | Значення | Опис |
|---|---|---|
| `HOTKEY_ALT` | `True` | Вимагати клавішу Alt |
| `HOTKEY_WIN` | `False` | Вимагати клавішу Win |
| `HOTKEY_CHAR` | `'q'` | Символ-тригер |
| `AUDIO_RATE` | `16000` | Частота дискретизації (Гц) |
| `DEBUG_MODE` | `True` | Виводити дебаг інформацію |

Щоб змінити мову транскрибування, відредагуйте параметр `language` у методі `DeepgramTranscriber.start()`:

```python
language="uk",  # Українська — змініть на "en", "de", "fr" тощо
```

### 🏗️ Архітектура

```
NOTwispr
├── AudioRecorder       — захоплює аудіо з мікрофону (PyAudio, PCM 16-bit 16kHz)
├── DeepgramTranscriber — стрімить аудіо через WebSocket до Deepgram Nova-3
├── TextInjector        — вставляє результат в активне вікно (Ctrl+V / посимвольно)
└── HotkeyManager       — глобальний слухач клавіатури (pynput), перемикач Alt+Q
```

### 🐛 Вирішення проблем

| Проблема | Рішення |
|---|---|
| `DEEPGRAM_API_KEY не знайдено` | Створіть `.env` з `.env.example` і додайте ключ |
| `Помилка встановлення PyAudio` | Використайте `pipwin install pyaudio` або завантажте wheel вручну |
| `Хоткей не спрацьовує` | Запустіть як адміністратор або перевірте конфлікт із іншими програмами |
| `Текст не вставляється` | Переконайтеся, що поле введення активне перед натисканням хоткею |
| `Порожня транскрипція` | Говоріть голосніше/ближче до мікрофону; перевірте, що мікрофон не вимкнено |

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">Made with ❤️ as a free alternative to paid voice dictation tools.</p>
