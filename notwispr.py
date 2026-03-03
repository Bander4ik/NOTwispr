"""
NOTwispr — Локальна альтернатива Wispr (голосовий диктатор з автонабором).

Як встановити:
    1. pip install -r requirements.txt
    2. Скопіюйте .env.example → .env і вставте ваш DEEPGRAM_API_KEY
    3. python notwispr.py

Як користуватися:
    • Натисніть Left Alt + Q — запис починається
    • Натисніть Left Alt + Q ще раз — запис зупиняється, текст вставляється
    • Ctrl+C — вихід

Вимоги:
    • Python 3.11+
    • Windows (для глобальних хоткеїв)
    • Мікрофон
    • DEEPGRAM_API_KEY (отримайте на https://console.deepgram.com/)
"""

import asyncio
import os
import sys
import time
import threading
import json

import pyaudio
import pyperclip
from pynput import keyboard
from pynput.keyboard import Key, Controller as KbController
from dotenv import load_dotenv
from deepgram import DeepgramClient
from deepgram.core.events import EventType

# ─────────────────────────── Конфігурація ────────────────────────────

load_dotenv()

DEEPGRAM_API_KEY = os.getenv("DEEPGRAM_API_KEY")
if not DEEPGRAM_API_KEY:
    print("❌ DEEPGRAM_API_KEY не знайдено! Створіть .env файл на основі .env.example")
    sys.exit(1)

# Аудіо: PCM 16-bit, 16kHz, mono
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 16000
AUDIO_CHUNK = 4096  # Більший чанк для стабільності WebSocket

# Затримка між натисканнями при друкуванні (секунди, для fallback режиму)
TYPE_DELAY = 0.005

# ХОТКЕЙ: Left Alt + Q
HOTKEY_WIN = False
HOTKEY_ALT = True
HOTKEY_CHAR = 'q'

# ДЕБАГ РЕЖИМ
DEBUG_MODE = True


# ─────────────────────────── AudioRecorder ───────────────────────────


class AudioRecorder:
    """Захоплює аудіо з мікрофону і пушить у callback на льоту."""
    def __init__(self):
        self._pya = pyaudio.PyAudio()
        self._stream = None
        self._recording = False
        self._lock = threading.Lock()
        self._on_audio_chunk = None  # Callback для відправки аудіо

    def set_callback(self, callback):
        """Встановлює callback для отримання аудіо-чанків."""
        self._on_audio_chunk = callback

    def start(self) -> bool:
        """Відкриває мікрофон. Повертає True, якщо ОК."""
        with self._lock:
            if self._recording: return True
            self._recording = True
        
        try:
            self._stream = self._pya.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK
            )
            # Запускаємо цикл читання
            self._read_thread = threading.Thread(target=self._run_read_loop, daemon=True)
            self._read_thread.start()
            return True
        except Exception as e:
            print(f"❌ Помилка мікрофону: {e}")
            with self._lock: self._recording = False
            return False

    def _run_read_loop(self):
        """Фоновий цикл читання аудіо."""
        while True:
            with self._lock:
                if not self._recording:
                    break
            
            try:
                if self._stream:
                    data = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                    if self._on_audio_chunk:
                        self._on_audio_chunk(data)
                    if DEBUG_MODE:
                        print(".", end="", flush=True)
            except Exception:
                break

    def stop(self):
        """Зупиняє запис."""
        with self._lock:
            if not self._recording: return
            self._recording = False

        # Спочатку дочекаємось завершення потоку читання
        if hasattr(self, "_read_thread") and self._read_thread.is_alive():
            self._read_thread.join(timeout=2.0)

        # Тепер безпечно закриваємо потік аудіо
        if self._stream:
            try:
                s = self._stream
                self._stream = None
                if not s.is_stopped():
                    s.stop_stream()
                s.close()
            except Exception:
                pass

    def terminate(self):
        try:
            self._pya.terminate()
        except:
            pass


# ─────────────────────────── DeepgramTranscriber ─────────────────────


class DeepgramTranscriber:
    """Підключається до Deepgram WebSocket, стрімить аудіо, збирає транскрипції."""

    def __init__(self):
        self._client = DeepgramClient(api_key=DEEPGRAM_API_KEY)
        self._connection = None
        self._ctx_manager = None
        self._transcript_parts = []
        self._is_connected = False
        self._lock = threading.Lock()
        self._done_event = threading.Event()

    def start(self) -> bool:
        """Відкриває WebSocket з'єднання з Deepgram."""
        try:
            self._transcript_parts = []
            self._done_event.clear()
            self._is_connected = False

            # Створюємо з'єднання через v1.connect.
            self._ctx_manager = self._client.listen.v1.connect(
                model="nova-3",
                language="uk",
                smart_format="true",
                encoding="linear16",
                sample_rate=str(AUDIO_RATE),
                channels=str(AUDIO_CHANNELS),
                vad_events="true",
                endpointing="true"
            )

            # Входимо в контекст-менеджер вручну
            self._connection = self._ctx_manager.__enter__()

            # Реєструємо обробники подій
            self._connection.on(EventType.OPEN, self._on_open)
            self._connection.on(EventType.MESSAGE, self._on_message)
            self._connection.on(EventType.ERROR, self._on_error)
            self._connection.on(EventType.CLOSE, self._on_close)

            # ВАЖЛИВО: Потрібно запустити прослуховування в окремому потоці,
            # інакше події на .on() ніколи не спрацюють.
            self._listen_thread = threading.Thread(
                target=self._connection.start_listening,
                daemon=True
            )
            self._listen_thread.start()

            if DEBUG_MODE:
                print("DEBUG: Deepgram з'єднання відкрито.")
            return True

        except Exception as e:
            print(f"❌ Помилка підключення до Deepgram: {e}")
            if hasattr(self, "_ctx_manager") and self._ctx_manager:
                try: self._ctx_manager.__exit__(None, None, None)
                except: pass
            return False

    def send_audio(self, data: bytes):
        """Відправляє аудіо-чанк у Deepgram."""
        if self._connection and self._is_connected:
            try:
                self._connection.send_media(data)
            except Exception as e:
                if DEBUG_MODE:
                    print(f"\nDEBUG send error: {e}")

    def finish(self) -> str:
        """Закриває з'єднання і повертає повний текст."""
        if self._connection:
            try:
                self._connection.finish()
            except Exception:
                pass

        # Виходимо з контекст-менеджера
        if self._ctx_manager:
            try:
                self._ctx_manager.__exit__(None, None, None)
            except Exception:
                pass
            self._ctx_manager = None
            self._connection = None

        # Чекаємо закриття з'єднання (до 3 секунд)
        self._done_event.wait(timeout=3.0)

        with self._lock:
            full_text = " ".join(self._transcript_parts).strip()
            self._transcript_parts = []

        return full_text

    # ── Обробники подій Deepgram ──

    def _on_open(self, *args, **kwargs):
        self._is_connected = True
        if DEBUG_MODE:
            print("DEBUG: Deepgram WebSocket відкрито, слухаю...")

    def _on_message(self, *args, **kwargs):
        """Обробляє вхідні повідомлення від Deepgram."""
        # У v6 повідомлення приходить у полі channel
        result = args[0] if args else kwargs.get("result")
        
        try:
            # Перевіряємо, чи це повідомлення з транскриптом
            if hasattr(result, "channel"):
                channel = result.channel
                if channel and hasattr(channel, "alternatives") and channel.alternatives:
                    transcript = channel.alternatives[0].transcript
                    # У v6 is_final може бути атрибутом
                    is_final = getattr(result, "is_final", True)

                    if transcript and is_final:
                        with self._lock:
                            self._transcript_parts.append(transcript)
                        if DEBUG_MODE:
                            print(f"\n📝 [{transcript}]", end="", flush=True)
        except Exception as e:
            if DEBUG_MODE:
                print(f"\nDEBUG message parse error: {e}")

    def _on_error(self, *args, **kwargs):
        error = args[1] if len(args) > 1 else args[0] if args else "unknown"
        if DEBUG_MODE:
            print(f"\n❌ Deepgram error: {error}")

    def _on_close(self, *args, **kwargs):
        self._is_connected = False
        self._done_event.set()
        if DEBUG_MODE:
            print("\nDEBUG: Deepgram з'єднання закрито.")


# ─────────────────────────── TextInjector ────────────────────────────


class TextInjector:
    """Копіює текст у clipboard і друкує у активне вікно."""

    def __init__(self):
        self._kb = KbController()

    def inject(self, text: str):
        """
        1. Копіює текст у clipboard (fail-safe)
        2. Друкує текст у активне вікно через Ctrl+V
        """
        if not text:
            return

        try:
            pyperclip.copy(text)
        except Exception as e:
            print(f"⚠️ Не вдалося скопіювати в clipboard: {e}")

        try:
            time.sleep(0.05)
            self._kb.press(Key.ctrl)
            self._kb.press("v")
            self._kb.release("v")
            self._kb.release(Key.ctrl)
        except Exception as e:
            print(f"⚠️ Ctrl+V не спрацював: {e}")
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
    """Перемикач (Toggle): натиснув Alt + Q — почав, натиснув ще раз — зупинив.
    Використовуємо Listener, бо він надійніший за GlobalHotKeys на Windows.
    """

    def __init__(self, on_toggle):
        self._on_toggle = on_toggle
        self._listener = None
        self._win_pressed = False
        self._alt_pressed = False
        self._char_pressed = False

    def _on_press(self, key):
        if key in (Key.alt_l, Key.alt_r, Key.alt, Key.alt_gr):
            self._alt_pressed = True
        elif key in (Key.cmd, Key.cmd_l, Key.cmd_r):
            self._win_pressed = True

        try:
            is_char = False
            if hasattr(key, 'char') and key.char and key.char.lower() == HOTKEY_CHAR:
                is_char = True
            
            if is_char:
                # Перевіряємо умови хоткею
                win_match = (self._win_pressed == HOTKEY_WIN)
                alt_match = (self._alt_pressed == HOTKEY_ALT)
                
                if win_match and alt_match and not self._char_pressed:
                    self._char_pressed = True
                    self._on_toggle()
        except Exception:
            pass

    def _on_release(self, key):
        if key in (Key.alt_l, Key.alt_r, Key.alt, Key.alt_gr):
            self._alt_pressed = False
        elif key in (Key.cmd, Key.cmd_l, Key.cmd_r):
            self._win_pressed = False
        
        try:
            if hasattr(key, 'char') and key.char and key.char.lower() == HOTKEY_CHAR:
                self._char_pressed = False
        except Exception:
            pass

    def start(self):
        """Запускає слухача у фоновому потоці."""
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()


# ─────────────────────────── Головний модуль ─────────────────────────


class NOTwispr:
    """Головний клас — зв'язує всі модулі разом."""

    def __init__(self):
        self._recorder = AudioRecorder()
        self._transcriber = DeepgramTranscriber()
        self._injector = TextInjector()
        self._hotkey = HotkeyManager(
            on_toggle=self._async_toggle,
        )
        self._is_recording = False
        self._state_lock = threading.Lock()
        self._action_lock = threading.Lock()

    def _async_toggle(self):
        """Неблокуючий callback: запускає справжню логіку у фоновому потоці."""
        if self._action_lock.acquire(blocking=False):
            threading.Thread(target=self._run_toggle, daemon=True).start()

    def _run_toggle(self):
        """Справжня логіка перемикання стану запису."""
        try:
            with self._state_lock:
                if self._is_recording:
                    # ── СТОП ──
                    self._is_recording = False
                    print("\n\n🛑 Зупинка запису...")
                    
                    self._recorder.stop()
                    text = self._transcriber.finish()

                    if text:
                        print(f"✅ Транскрипція: {text}")
                        self._injector.inject(text)
                    else:
                        print("⚠️  Порожній результат.")
                else:
                    # ── СТАРТ ──
                    if not self._transcriber.start():
                        return
                    
                    # Встановлюємо callback: аудіо з мікрофону → Deepgram
                    self._recorder.set_callback(self._transcriber.send_audio)
                    
                    if not self._recorder.start():
                        self._transcriber.finish()
                        return

                    self._is_recording = True
                    hk_str = "Left Alt + Q" if not HOTKEY_WIN else f"Win + Alt + {HOTKEY_CHAR.upper()}"
                    print(f"\n🎙️  Запис... (натисніть {hk_str} щоб зупинити)")
        finally:
            self._action_lock.release()

    def run(self):
        """Запускає NOTwispr."""
        print("=" * 55)
        print("  🎤 NOTwispr — Голосовий диктатор")
        print("=" * 55)
        print(f"  Двигун:  Deepgram Nova-3")
        print(f"  Мова:    Українська")
        
        hk_str = "Left Alt + Q" if not HOTKEY_WIN else f"Win + Alt + {HOTKEY_CHAR.upper()}"
        print(f"  Хоткей:  {hk_str} (натиснути для старт/стоп)")
        print(f"  Вихід:   Ctrl+C")
        print("=" * 55)
        print()

        self._hotkey.start()
        print(f"✅ Готово! Натисніть {hk_str} для запису.\n")

        try:
            # Тримаємо головний потік живим
            while True:
                time.sleep(1)
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
