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
from google.genai import types

# ─────────────────────────── Конфігурація ────────────────────────────

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("❌ GEMINI_API_KEY не знайдено! Створіть .env файл на основі .env.example")
    sys.exit(1)

# Модель — обов'язково повний ID для потрапляння у безкоштовну квоту Native Audio
MODEL = "gemini-2.5-flash-native-audio-preview-12-2025"

# Хоткей — перемикач (toggle)
# Left Alt + Q
HOTKEY_COMBO = "<alt_l>+q"

# Аудіо: PCM 16-bit, 16kHz, mono (вимога Gemini Live API)
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_CHANNELS = 1
AUDIO_RATE = 16000
AUDIO_CHUNK = 1024

# Затримка між натисканнями при друкуванні (секунди, для fallback режиму)
TYPE_DELAY = 0.005

# Затримка фіналізації (секунди) для захоплення останніх слів після відпускання кнопки
STOP_DELAY = 1.0

# ДЕБАГ РЕЖИМ (включіть True, щоб бачити сирі відповіді API)
DEBUG_MODE = True

# Поріг гучності. Все, що нижче - тиша (настроїш під свій мікрофон)
# Для потужних мікрофонів біля рота оптимально 30-45
SILENCE_THRESHOLD = 40.0

# Системний промпт для Gemini (точна копія з вимог — не змінювати!)
SYSTEM_INSTRUCTION = (
    "Ти — професійний транскрибатор. Твоя єдина задача: перевести аудіо в текст, "
    "ідеально розставити пунктуацію і повернути ТІЛЬКИ текст.\n"
    "ВАЖЛИВО: ТРАНСКРИБУЙ УСЕ АУДІО ВІД ПОЧАТКУ ДО КІНЦЯ. "
    "НЕ ЗУПИНЯЙСЯ і не переривайся, якщо в аудіо є довгі ПАУЗИ чи тиша. "
    "Продовжуй розпізнавати все, що сказано після будь-яких проміжків.\n"
    "Моя основна мова — українська, але з англійськими термінами та ІТ-сленгом. "
    "Англійські слова пиши англійською (наприклад, 'deploy', 'code'). "
    "Жодних роздумів, коментарів чи розмов — тільки транскрипція."
)

# ─────────────────────────── AudioRecorder ───────────────────────────


class AudioRecorder:
    """Захоплює аудіо, ріже тишу скальпелем і пушить у чергу на льоту."""
    def __init__(self, loop: asyncio.AbstractEventLoop, audio_queue: asyncio.Queue):
        self._pya = pyaudio.PyAudio()
        self._stream = None
        self._recording = False
        self._mute_debug = False # Чи перестати малювати крапки
        self._lock = threading.Lock()
        self._loop = loop
        self._audio_queue = audio_queue

    def set_mute_debug(self, mute: bool):
        """Зупиняє малювання крапок (коли текст вже отримано)."""
        self._mute_debug = mute

    def _get_rms(self, data: bytes) -> float:
        """Обчислює гучність чанку."""
        import struct
        import math
        count = len(data) // 2
        shorts = struct.unpack("%dh" % count, data)
        sum_squares = sum(s**2 for s in shorts)
        return math.sqrt(sum_squares / count) if count > 0 else 0.0

    def start(self) -> bool:
        """Відкриває мікрофон. Повертає True, якщо ОК."""
        with self._lock:
            if self._recording: return True
            self._recording = True
            self._mute_debug = False
        
        try:
            self._stream = self._pya.open(
                format=AUDIO_FORMAT,
                channels=AUDIO_CHANNELS,
                rate=AUDIO_RATE,
                input=True,
                frames_per_buffer=AUDIO_CHUNK
            )
            # Запускаємо цикл читання, якщо він не активний
            if not hasattr(self, "_read_thread") or not self._read_thread.is_alive():
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
                if not self._recording and not self._stream: 
                    break # Повністю виходимо, якщо запис вимкнено і стрім закрито
                if not self._recording:
                    time.sleep(0.1)
                    continue
            
            try:
                if self._stream:
                    data = self._stream.read(AUDIO_CHUNK, exception_on_overflow=False)
                    rms = self._get_rms(data)
                    
                    if rms > SILENCE_THRESHOLD:
                        if DEBUG_MODE and not self._mute_debug:
                            print(".", end="", flush=True) 
                        self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, data)
            except Exception:
                break

    def stop(self):
        """Зупиняє запис з невеликою затримкою, щоб встигнути дослухати останнє слово."""
        def _delayed_stop():
            if STOP_DELAY > 0:
                time.sleep(STOP_DELAY)
            
            with self._lock:
                if not self._recording: return
                self._recording = False

            # Сигнал закінчення аудіо для API
            self._loop.call_soon_threadsafe(self._audio_queue.put_nowait, b"END_OF_STREAM")

            if self._stream:
                try:
                    s = self._stream
                    self._stream = None
                    s.stop_stream()
                    s.close()
                except Exception:
                    pass
            if hasattr(self, "_read_thread"):
                self._read_thread.join(timeout=0.5)

        threading.Thread(target=_delayed_stop, daemon=True).start()

    def terminate(self):
        try:
            self._pya.terminate()
        except:
            pass


# ─────────────────────────── GeminiTranscriber ──────────────────────


class GeminiTranscriber:
    """Підтримує постійний стрім. Віддає текст, коли стрім закінчено."""
    def __init__(self):
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        self._config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=SYSTEM_INSTRUCTION,
            input_audio_transcription=types.AudioTranscriptionConfig()
        )

    async def stream_and_transcribe(self, audio_queue: asyncio.Queue) -> str:
        input_text_parts = []
        model_text_parts = []
        try:
            async with self._client.aio.live.connect(model=MODEL, config=self._config) as session:
                if DEBUG_MODE:
                    print("DEBUG: З'єднання відкрито, готовий слухати.")

                async def send_audio():
                    try:
                        while True:
                            # Чекаємо чанк з черги
                            chunk = await audio_queue.get()
                            if chunk == b"END_OF_STREAM":
                                if DEBUG_MODE: print("\nDEBUG: Кінець аудіо-потоку.")
                                try:
                                    await session.send_realtime_input(audio_stream_end=True)
                                except: pass
                                break
                            
                            # Стрімимо шматки аудіо на льоту
                            # Вказуємо rate для надійності
                            await session.send_realtime_input(
                                audio={"data": chunk, "mime_type": "audio/pcm;rate=16000"}
                            )
                    except Exception as e:
                        if DEBUG_MODE: print(f"\nDEBUG send_audio error: {e}")

                async def receive_responses():
                    try:
                        async for response in session.receive():
                            sc = response.server_content
                            if not sc: continue

                            if sc.input_transcription and sc.input_transcription.text:
                                text = sc.input_transcription.text
                                input_text_parts.append(text)
                                if DEBUG_MODE:
                                    print(f"| {text}", end="", flush=True)

                            # Виходимо одразу як Gemini сигналізує про завершення ходу.
                            # Це усуває затримку 20-40с.
                            if sc.turn_complete:
                                if DEBUG_MODE: print("\nDEBUG: turn_complete отримано, виходимо.")
                                break
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        if DEBUG_MODE: print(f"\nDEBUG receive error: {e}")

                # Запускаємо надсилання та отримання паралельно через таски
                send_task = asyncio.create_task(send_audio())
                receive_task = asyncio.create_task(receive_responses())

                # Чекаємо, поки все аудіо з черги піде в мережу (включно з STOP_DELAY)
                await send_task
                
                # Чекаємо або turn_complete (швидкий шлях), або таймаут як fallback.
                # 5 секунд більш ніж достатньо — якщо turn_complete не прийшов, щось пішло не так.
                finish_timeout = 5.0
                try:
                    await asyncio.wait_for(asyncio.shield(receive_task), timeout=finish_timeout)
                except asyncio.TimeoutError:
                    if DEBUG_MODE: print(f"\nDEBUG: Очікування фіналізації завершено по таймауту {finish_timeout}с.")
                finally:
                    if not receive_task.done():
                        receive_task.cancel()
                        try: await receive_task
                        except: pass

        except Exception as e:
            print(f"❌ Помилка Gemini API: {e}")
            return ""

        if not input_text_parts:
            return ""

        full_text = "".join(input_text_parts).strip()

        import re
        full_text = re.sub(r"\*\*.*?\*\*", "", full_text, flags=re.DOTALL)
        
        # Видаляємо фрази-маркери Gemini
        boilerplate = [
            r"I have transcribed.*?:",
            r"I've successfully transcribed.*?:",
            r"Transcribing Ukrainian Phrase.*?:",
            r"Here is the transcription:",
            r"The Ukrainian phrase is:",
            r"I've decided to interpret.*?:",
            r"My final output will correct.*?:",
        ]
        for pattern in boilerplate:
            full_text = re.sub(pattern, "", full_text, flags=re.IGNORECASE | re.DOTALL)

        blocks = [b.strip() for b in full_text.split("\n") if b.strip()]
        if not blocks: return ""
        
        for block in reversed(blocks):
            if re.search(r'[а-яА-ЯіїєґІЇЄҐ]', block):
                return block.strip(' "«»')
        return blocks[-1].strip(' "«»')




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
    """Перемикач (Toggle): натиснув Alt+Q — почав, натиснув ще раз — зупинив.
    Використовуємо Listener, бо він надійніший за GlobalHotKeys на Windows.
    """

    def __init__(self, on_toggle):
        self._on_toggle = on_toggle
        self._listener = None
        self._alt_pressed = False
        self._q_pressed = False

    def _on_press(self, key):
        # Перевіряємо Alt (будь-який)
        if key in (Key.alt_l, Key.alt_r, Key.alt, Key.alt_gr):
            self._alt_pressed = True
            return

        try:
            # Перевіряємо Q (ігноруючи розкладку через vk або порівняння char)
            is_q = False
            if hasattr(key, 'char') and key.char and key.char.lower() == 'q':
                is_q = True
            elif hasattr(key, 'vk') and key.vk == 81: # VK_Q = 81
                is_q = True
            
            if is_q:
                if self._alt_pressed and not self._q_pressed:
                    self._q_pressed = True
                    self._on_toggle()
        except Exception:
            pass

    def _on_release(self, key):
        if key in (Key.alt_l, Key.alt_r, Key.alt, Key.alt_gr):
            self._alt_pressed = False
        
        try:
            is_q = False
            if hasattr(key, 'char') and key.char and key.char.lower() == 'q':
                is_q = True
            elif hasattr(key, 'vk') and key.vk == 81:
                is_q = True
            
            if is_q:
                self._q_pressed = False
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
        self._recorder = None
        self._transcriber = GeminiTranscriber()
        self._injector = TextInjector()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._audio_queue: asyncio.Queue | None = None
        self._hotkey = HotkeyManager(
            on_toggle=self._handle_toggle,
        )
        self._is_recording = False
        self._is_processing = False
        self._state_lock = threading.Lock()

    def _handle_toggle(self):
        """Callback: перемикання стану запису."""
        if not self._loop or not self._audio_queue:
            return

        with self._state_lock:
            if self._is_recording:
                # Зупиняємо
                if self._recorder:
                    self._recorder.stop()
                self._is_recording = False
                if DEBUG_MODE: print("\nDEBUG: Натиснуто Стоп.")
            else:
                # Починаємо
                if self._is_processing:
                    if DEBUG_MODE: print("\nDEBUG: Все ще обробляється попередній текст...")
                    return
                
                if not self._recorder.start():
                    return
                
                self._is_recording = True
                self._is_processing = True
                if DEBUG_MODE: print("\nDEBUG: Натиснуто Старт.")

                # Очищуємо чергу
                while not self._audio_queue.empty():
                    try: self._audio_queue.get_nowait()
                    except: break
                
                asyncio.run_coroutine_threadsafe(self._process(), self._loop)

    async def _process(self):
        """Транскрибує аудіо з черги і вводить текст."""
        try:
            text = await self._transcriber.stream_and_transcribe(self._audio_queue)
            if self._recorder:
                self._recorder.set_mute_debug(True)
            
            if text:
                print(f"✅ Транскрипція: {text}")
                self._injector.inject(text)
            else:
                print("\n⚠️  Порожній результат.")
        except Exception as e:
            print(f"\n❌ Помилка: {e}")
        finally:
            # Скидаємо прапорець обробки ПІСЛЯ завершення асинхронної задачі
            with self._state_lock:
                self._is_processing = False

    async def _run_forever(self):
        """Тримає asyncio loop активним та ініціалізує асинхронні частини."""
        self._loop = asyncio.get_running_loop()
        # Створюємо чергу саме в працюючому циклі!
        self._audio_queue = asyncio.Queue()
        self._recorder = AudioRecorder(self._loop, self._audio_queue)
        
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
        print(f"  Хоткей:  Left Alt + Q (натиснути для старт/стоп)")
        print(f"  Вихід:   Ctrl+C")
        print("=" * 55)
        print()

        # Запускаємо слухача хоткеїв
        self._hotkey.start()
        print("✅ Готово! Натисніть Left Alt + Q для запису.\n")

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
