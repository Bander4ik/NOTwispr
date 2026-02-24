# NOTwispr 🎤

Локальна, швидка та безкоштовна альтернатива "Wispr". Голосовий диктатор, який використовує **Gemini Live API** для миттєвої транскрипції та автоматичного набору тексту у будь-яке активне вікно.

## 🚀 Основні можливості

- **Push-to-talk:** Натисніть і тримайте хоткей для запису.
- **Розумна транскрипція:** Використовує модель `gemini-2.5-flash-native-audio-preview-12-2025`.
- **UA-EN Мікс:** Ідеально розпізнає суміш української мови та ІТ-сленгу.
- **Clipboard Fail-safe:** Текст завжди копіюється в буфер обміну перед друком.
- **Авто-набір:** Автоматично вставляє текст через `Ctrl+V` у активне поле.

## 🛠 Установка

1. **Клонуйте репозиторій:**
   ```bash
   git clone https://github.com/USER_NAME/NOTwispr.git
   cd NOTwispr
   ```

2. **Встановіть залежності:**
   ```bash
   pip install -r requirements.txt
   ```
   *Примітка: на Windows може знадобитись встановлення `portaudio` для `pyaudio`.*

3. **Налаштуйте API ключ:**
   - Скопіюйте `.env.example` в `.env`
   - Отримайте безкоштовний ключ на [Google AI Studio](https://aistudio.google.com/apikey)
   - Вставте його: `GEMINI_API_KEY=your_key_here`

## ⌨️ Як користуватися

1. Запустіть скрипт:
   ```bash
   python notwispr.py
   ```
2. Натисніть і тримайте **Left Alt + Q**.
3. Говоріть у мікрофон.
4. Відпустіть клавіші — текст з'явиться за 1-2 секунди.

## 📦 Стек
- **Python 3.11+**
- **google-genai** (WebSockets)
- **PyAudio** (Audio capture)
- **pynput** (Global Hotkeys)
- **pyperclip** (Clipboard)

## 📄 Ліцензія
MIT
