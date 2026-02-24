"""
NOTwispr — Локальна альтернатива Wispr (голосовий диктатор з автонабором).

Як встановити:
    1. pip install -r requirements.txt
    2. Скопіюйте .env.example → .env і вставте ваш GEMINI_API_KEY
    3. python notwispr.py

Як користуватися:
    • Натисніть і тримайте Left Alt + Q — йде запис з мікрофону
    • Відпустіть — аудіо відправляється в Gemini, текст друкується в активне вікно
    • Ctrl+C — вихід

Вимоги:
    • Python 3.11+
    • Windows (для глобальних хоткеїв)
    • Мікрофон
    • GEMINI_API_KEY (безкоштовно: https://aistudio.google.com/apikey)
"""

import asyncio
import os
import sys
import time
import threading
from io import BytesIO

import pyaudio
import pyperclip
from pynput import keyboard
from pynput.keyboard import Key, Controller as KbController
from dotenv import load_dotenv
from google import genai

# ─────────────────────────── Конфігурація ────────────────────────────

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY не знайдено! Створіть .env файл на основі .env.example")
    sys.exit(1)

# Модель — обов'язково повний ID для потрапляння у безкоштовну квоту Native Audio
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# Хоткей — push-to-talk
HOTKEY_MODIFIER = Key.alt_l   # Left Alt
HOTKEY_KEY = "q"              # Q

# Аудіо: PCM 16-bit, 16kHz, mono (вимога Gemini Live API)
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 16000
AUDIO_CHUNK = 1024

# Затримка між натисканнями при друкуванні (секунди)
TYPE_DELAY = 0.005

# Системний промпт для Gemini (точна копія з вимог — не змінювати!)
SYSTEM_INSTRUCTION = (
    "Ти — ідеальний транскрибатор. Твоя єдина задача: перевести аудіо в текст, "
    "виправити дрібні помилки, ідеально розставити пунктуацію і повернути ТІЛЬКИ текст. "
    "Жодних коментарів, привітань чи зайвих слів.\n"
    "ВАЖЛИВО: Моя основна мова — українська, але я часто змішую її з англійськими словами, "
    "ІТ-сленгом та термінами. Твоя задача — коректно розпізнавати цей мікс. "
    "Англійські слова пиши англійською, не роби з них потворний трансліт і не перекладай їх "
    "(наприклад, пиши 'deploy', а не 'деплой' чи 'розгортання'). "
    "Зберігай мій природний стиль спілкування."
)

# ─────────────────────────── AudioRecorder ───────────────────────────


class AudioRecorder:
    """Захоплює аудіо з мікрофону у буфер (push-to-talk)."""

    def __init__(self):
        self._pya = pyaudio.PyAudio()
        self._stream = None
        self._frames: list[bytes] = []
        self._recording = False
        self._lock = threading.Lock()

    def start(self):
        """Починає запис з дефолтного мікрофону."""
        with self._lock:
            if self._recording:
                return
            self._frames = []
            self._recording = True

        try:
            mic_info = self._pya.get_default_input_device_info()
            self._stream = self._pya.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                input_device_index=int(mic_info["index"]),
                frames_per_buffer=AUDIO_CHUNK,
            )
        except Exception as e:
            print(f"❌ Не вдалося відкрити мікрофон: {e}")
            with self._lock:
                self._recording = False
            return

        # Читаємо аудіо у фоновому потоці
        def _read_loop():
            while True:
                with self._lock:
                    if not self._recording:
                        break
                try:
                    data = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                    self._frames.append(data)
                except Exception:
                    break

        self._read_thread = threading.Thread(target=_read_loop, daemon=True)
        self._read_thread.start()

    def stop(self) -> bytes:
        """Зупиняє запис і повертає зібране аудіо як bytes."""
        with self._lock:
            self._recording = False

        if hasattr(self, "_read_thread"):
            self._read_thread.join(timeout=2.0)

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        audio_data = b"".join(self._frames)
        self._frames = []
        return audio_data

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._recording

    def terminate(self):
        """Звільняє ресурси PyAudio."""
        try:
            if self._stream:
                self._stream.close()
        except Exception:
            pass
        self._pya.terminate()


# ─────────────────────────── GeminiTranscriber ──────────────────────


class GeminiTranscriber:
    """Відправляє аудіо в Gemini Live API і отримує текст."""

    def __init__(self):
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._config = {
            "response_modalities": ["TEXT"],
            "system_instruction": SYSTEM_INSTRUCTION,
        }

    async def transcribe(self, audio_data: bytes) -> str:
        """
        Відкриває WebSocket-сесію, стрімить аудіо чанками і збирає текстову відповідь.
        """
        if not audio_data:
            return ""

        text_parts: list[str] = []

        try:
            async with self._client.aio.live.connect(
                model=MODEL,
                config=self._config,
            ) as session:

                # Стрімимо аудіо чанками
                chunk_size = AUDIO_CHUNK * 2  # 2 bytes per sample (16-bit)
                for i in range(0, len(audio_data), chunk_size):
                    chunk = audio_data[i : i + chunk_size]
                    await session.send_realtime_input(
                        audio={"data": chunk, "mime_type": "audio/pcm"}
                    )
                    # Невелика пауза щоб не перевантажити буфер
                    await asyncio.sleep(0.01)

                # Сигналізуємо що аудіо закінчилось — закриваємо відправку
                # і чекаємо відповідь
                await session.send_realtime_input(end_of_turn=True)

                # Збираємо текстову відповідь
                turn = session.receive()
                async for response in turn:
                    if response.server_content and response.server_content.model_turn:
                        for part in response.server_content.model_turn.parts:
                            if hasattr(part, "text") and part.text:
                                text_parts.append(part.text)

        except Exception as e:
            print(f"❌ Помилка Gemini API: {e}")
            return ""

        return "".join(text_parts).strip()


# ─────────────────────────── TextInjector ────────────────────────────


class TextInjector:
    """Копіює текст у clipboard і друкує у активне вікно."""

    def __init__(self):
        self._kb = KbController()

    def inject(self, text: str):
        """
        1. Копіює текст у clipboard (fail-safe)
        2. Друкує текст у активне вікно через Ctrl+V (надійніший за посимвольний набір)
        """
        if not text:
            return

        # Крок 1: Завжди копіюємо у clipboard (fail-safe)
        try:
            pyperclip.copy(text)
        except Exception as e:
            print(f"⚠️ Не вдалося скопіювати в clipboard: {e}")

        # Крок 2: Вставляємо через Ctrl+V (надійніше за посимвольний друк)
        # Це дозволяє уникнути проблем з розкладкою клавіатури та Unicode
        try:
            time.sleep(0.05)  # Маленька пауза перед вставкою
            self._kb.press(Key.ctrl)
            self._kb.press("v")
            self._kb.release("v")
            self._kb.release(Key.ctrl)
        except Exception as e:
            print(f"⚠️ Ctrl+V не спрацював: {e}")
            # Fallback: посимвольний друк
            self._type_char_by_char(text)

    def _type_char_by_char(self, text: str):
        """Fallback — друкує текст посимвольно."""
        try:
            for char in text:
                self._kb.type(char)
                time.sleep(TYPE_DELAY)
        except Exception as e:
            print(f"⚠️ Посимвольний друк не спрацював: {e}")
            print(f"📋 Текст доступний у clipboard — вставте Ctrl+V вручну")


# ─────────────────────────── HotkeyManager ───────────────────────────


class HotkeyManager:
    """Push-to-talk: тримаєш Alt+Q = пишеш, відпустив = транскрипція."""

    def __init__(self, on_start, on_stop):
        self._on_start = on_start
        self._on_stop = on_stop
        self._modifier_pressed = False
        self._hotkey_active = False
        self._listener = None

    def _on_press(self, key):
        # Перевіряємо модифікатор (Left Alt)
        if key == HOTKEY_MODIFIER:
            self._modifier_pressed = True
            return

        # Перевіряємо основну клавішу (Q)
        try:
            if hasattr(key, "char") and key.char == HOTKEY_KEY:
                if self._modifier_pressed and not self._hotkey_active:
                    self._hotkey_active = True
                    self._on_start()
        except AttributeError:
            pass

    def _on_release(self, key):
        # Відпустили модифікатор
        if key == HOTKEY_MODIFIER:
            self._modifier_pressed = False
            if self._hotkey_active:
                self._hotkey_active = False
                self._on_stop()
            return

        # Відпустили основну клавішу
        try:
            if hasattr(key, "char") and key.char == HOTKEY_KEY:
                if self._hotkey_active:
                    self._hotkey_active = False
                    self._on_stop()
        except AttributeError:
            pass

    def start(self):
        """Запускає слухача хоткеїв у фоновому потоці."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        """Зупиняє слухача."""
        if self._listener:
            self._listener.stop()


# ─────────────────────────── Головний модуль ─────────────────────────


class NOTwispr:
    """Головний клас — зв'язує всі модулі разом."""

    def __init__(self):
        self._recorder = AudioRecorder()
        self._transcriber = GeminiTranscriber()
        self._injector = TextInjector()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._hotkey = HotkeyManager(
            on_start=self._handle_start,
            on_stop=self._handle_stop,
        )

    def _handle_start(self):
        """Callback: натиснуто хоткей — почати запис."""
        print("🎙️  Запис...")
        self._recorder.start()

    def _handle_stop(self):
        """Callback: відпущено хоткей — зупинити запис і транскрибувати."""
        audio_data = self._recorder.stop()

        if not audio_data:
            print("⚠️  Порожній запис, пропускаю.")
            return

        duration_sec = len(audio_data) / (AUDIO_RATE * 2)  # 2 bytes per sample
        print(f"⏹️  Зупинено ({duration_sec:.1f}с). Транскрибую...")

        # Запускаємо транскрипцію в asyncio event loop
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._process(audio_data), self._loop
            )
            # Не блокуємо потік хоткея — результат обробиться в _process
        else:
            print("⚠️  Event loop не запущено!")

    async def _process(self, audio_data: bytes):
        """Транскрибує аудіо і вводить текст."""
        try:
            text = await self._transcriber.transcribe(audio_data)
            if text:
                print(f"✅ Транскрипція: {text}")
                self._injector.inject(text)
            else:
                print("⚠️  Порожня транскрипція — можливо, тиша або помилка API.")
        except Exception as e:
            print(f"❌ Помилка обробки: {e}")

    async def _run_forever(self):
        """Тримає asyncio loop активним."""
        self._loop = asyncio.get_running_loop()
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    def run(self):
        """Запускає NOTwispr."""
        print("=" * 55)
        print("  🎤 NOTwispr — Голосовий диктатор")
        print("=" * 55)
        print(f"  Модель:  {MODEL}")
        print(f"  Хоткей:  Left Alt + Q (тримайте для запису)")
        print(f"  Вихід:   Ctrl+C")
        print("=" * 55)
        print()

        # Запускаємо слухача хоткеїв
        self._hotkey.start()
        print("✅ Готово! Тримайте Left Alt + Q для запису голосу.\n")

        # Запускаємо головний asyncio loop
        try:
            asyncio.run(self._run_forever())
        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _cleanup(self):
        """Звільняє всі ресурси."""
        print("\n🛑 Завершення...")
        self._hotkey.stop()
        self._recorder.terminate()
        print("👋 До побачення!")


# ─────────────────────────── Точка входу ─────────────────────────────

if __name__ == "__main__":
    app = NOTwispr()
    app.run()
