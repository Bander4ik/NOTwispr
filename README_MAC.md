# 🍎 NOTwispr — macOS Guide

> **⚠️ NOTwispr was originally built for Windows.**
> On macOS it works, but requires **one manual code change** and some additional setup steps.

---

## 🇬🇧 English — macOS Installation

### What needs to be changed

On macOS, **paste is `⌘V` (Cmd+V)**, not `Ctrl+V` like on Windows.
The app was built for Windows, so you need to change **one line** in `notwispr.py` manually.

#### Required code change

Open `notwispr.py`, find the `inject` method inside the `TextInjector` class (around line 310):

**Find this:**
```python
self._kb.press(Key.ctrl)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.ctrl)
```

**Replace with:**
```python
self._kb.press(Key.cmd)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.cmd)
```

That's the only code change needed.

---

### 📋 Requirements

| Requirement | Version / Notes |
|---|---|
| **OS** | macOS 12 Monterey or later (recommended) |
| **Python** | 3.11 or higher |
| **Homebrew** | Package manager for macOS — [brew.sh](https://brew.sh) |
| **Microphone** | Built-in or external |
| **Internet** | Required (for Deepgram API) |
| **Deepgram API Key** | Free at [console.deepgram.com](https://console.deepgram.com/) |

---

### 🚀 Installation

#### Step 1 — Install Homebrew (if not already installed)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Step 2 — Install PortAudio (required for PyAudio on macOS)

```bash
brew install portaudio
```

#### Step 3 — Clone the repository

```bash
git clone https://github.com/Bander4ik/NOTwispr.git
cd NOTwispr
```

#### Step 4 — Create and activate a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Step 5 — Install Python dependencies

```bash
pip install -r requirements.txt
```

> ✅ PyAudio should install without issues now that PortAudio is installed via Homebrew.

#### Step 6 — Apply the code fix (Cmd+V instead of Ctrl+V)

Open `notwispr.py` in any editor and find this block (around line 310):

```python
self._kb.press(Key.ctrl)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.ctrl)
```

Replace `Key.ctrl` with `Key.cmd` (both lines):

```python
self._kb.press(Key.cmd)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.cmd)
```

Save the file.

#### Step 7 — Create the `.env` file

```bash
cp .env.example .env
```

Open `.env` and paste your Deepgram API key:

```env
DEEPGRAM_API_KEY=your_actual_api_key_here
```

Get a free key at [console.deepgram.com](https://console.deepgram.com/) — you get **$200 free credit**.

#### Step 8 — Grant Accessibility permissions (pynput requirement)

macOS blocks global keyboard listeners by default. You must allow it:

1. Open **System Settings** → **Privacy & Security** → **Accessibility**
2. Click the **`+`** button
3. Add your **Terminal app** (Terminal, iTerm2, or VS Code — whichever you use to run the script)
4. Make sure the toggle is **ON**

> ⚠️ Without this step, the `Alt+Q` hotkey will **not work**.

#### Step 9 — Run

```bash
python3 notwispr.py
```

---

### 🎮 Usage

| Action | Shortcut |
|---|---|
| **Start recording** | `Left Alt + Q` (Option key on Mac keyboard) |
| **Stop recording & paste text** | `Left Alt + Q` again |
| **Exit** | `Ctrl+C` in terminal |

> 💡 On a Mac keyboard, `Alt` = `Option (⌥)`. So the hotkey is **`⌥ Option + Q`**.

1. Place your cursor in the text field where you want the text to appear
2. Press `Option + Q` — recording starts
3. Speak naturally
4. Press `Option + Q` again — text is transcribed and pasted automatically via `⌘V`

---

### 🐛 Troubleshooting

| Problem | Solution |
|---|---|
| `PyAudio install fails` | Run `brew install portaudio` first, then `pip install pyaudio` |
| `Hotkey doesn't work` | Add Terminal to **Accessibility** in System Settings (Step 8) |
| `Text not pasting` | Make sure you applied the `Key.cmd` fix (Step 6) |
| `Permission denied` errors | Re-check Accessibility settings; try restarting Terminal |
| `Empty transcription` | Check mic permissions in **System Settings → Privacy → Microphone** |
| `python: command not found` | Use `python3` instead of `python` |

---

## 🇺🇦 Українська — Встановлення на macOS

### Що потрібно змінити

На macOS **вставка — це `⌘V` (Cmd+V)**, а не `Ctrl+V` як на Windows.
Програма написана для Windows, тому потрібно вручну змінити **один рядок** у `notwispr.py`.

#### Необхідна зміна коду

Відкрий `notwispr.py`, знайди метод `inject` у класі `TextInjector` (приблизно рядок 310):

**Знайди:**
```python
self._kb.press(Key.ctrl)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.ctrl)
```

**Заміни на:**
```python
self._kb.press(Key.cmd)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.cmd)
```

Це єдина зміна в коді.

---

### 📋 Вимоги

| Вимога | Версія / Примітки |
|---|---|
| **ОС** | macOS 12 Monterey або новіший |
| **Python** | 3.11 або вище |
| **Homebrew** | Менеджер пакетів для macOS — [brew.sh](https://brew.sh) |
| **Мікрофон** | Вбудований або зовнішній |
| **Інтернет** | Необхідний (для API Deepgram) |
| **Deepgram API Key** | Безкоштовно на [console.deepgram.com](https://console.deepgram.com/) |

---

### 🚀 Встановлення

#### Крок 1 — Встанови Homebrew (якщо ще не встановлено)

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### Крок 2 — Встанови PortAudio (потрібно для PyAudio на macOS)

```bash
brew install portaudio
```

#### Крок 3 — Клонуй репозиторій

```bash
git clone https://github.com/Bander4ik/NOTwispr.git
cd NOTwispr
```

#### Крок 4 — Створи та активуй віртуальне середовище

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Крок 5 — Встанови залежності Python

```bash
pip install -r requirements.txt
```

#### Крок 6 — Застосуй правку коду (Cmd+V замість Ctrl+V)

Відкрий `notwispr.py` у будь-якому редакторі, знайди цей блок (~рядок 310):

```python
self._kb.press(Key.ctrl)
self._kb.press("v")
self._kb.release("v")
self._kb.release(Key.ctrl)
```

Заміни `Key.ctrl` на `Key.cmd` (обидва рядки). Збережи файл.

#### Крок 7 — Налаштуй `.env` файл

```bash
cp .env.example .env
```

Відкрий `.env` і встав свій Deepgram API ключ:

```env
DEEPGRAM_API_KEY=твій_api_ключ_тут
```

#### Крок 8 — Дай дозвіл на Accessibility (обов'язково!)

macOS блокує глобальні слухачі клавіатури за замовчуванням:

1. Відкрий **Системні налаштування** → **Конфіденційність і безпека** → **Спеціальні можливості**
2. Натисни **`+`**
3. Додай своє **Terminal-додаток** (Terminal, iTerm2 або VS Code)
4. Переконайся, що перемикач **УВІМКНЕНИЙ**

> ⚠️ Без цього кроку хоткей `Option+Q` **не спрацює**.

#### Крок 9 — Запуск

```bash
python3 notwispr.py
```

---

### 🎮 Використання

| Дія | Комбінація |
|---|---|
| **Почати запис** | `Option (⌥) + Q` |
| **Зупинити і вставити текст** | `Option (⌥) + Q` ще раз |
| **Вийти** | `Ctrl+C` у терміналі |

> 💡 На клавіатурі Mac клавіша `Alt` = `Option (⌥)`.

---

### 🐛 Вирішення проблем

| Проблема | Рішення |
|---|---|
| `Помилка встановлення PyAudio` | Виконай `brew install portaudio` спочатку |
| `Хоткей не спрацьовує` | Додай Terminal у **Спеціальні можливості** (Крок 8) |
| `Текст не вставляється` | Переконайся, що застосував правку `Key.cmd` (Крок 6) |
| `Порожня транскрипція` | Перевір дозвіл на мікрофон у **Системні налаштування → Конфіденційність → Мікрофон** |
| `python: command not found` | Використовуй `python3` замість `python` |

---

<p align="center">🍎 macOS guide for <a href="README.md">NOTwispr</a></p>
