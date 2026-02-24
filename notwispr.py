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

# ДЕБАГ РЕЖИМ (включіть True, щоб бачити сирі відповіді API)
DEBUG_MODE = True

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

    def get_rms(self, debug_frames: bytes) -> float:
        """Обчислює RMS (середньоквадратичну гучність) для перевірки мікрофону."""
        import math
        import struct
        if not debug_frames:
            return 0.0
        count = len(debug_frames) // 2
        format = "%dh" % count
        shorts = struct.unpack(format, debug_frames)
        sum_squares = sum(s**2 for s in shorts)
        return math.sqrt(sum_squares / count) if count > 0 else 0.0


# ─────────────────────────── GeminiTranscriber ──────────────────────


class GeminiTranscriber:
    """Відправляє аудіо в Gemini Live API і отримує ТІЛЬКИ текстову транскрипцію."""

    def __init__(self):
        self._client = genai.Client(api_key=GEMINI_API_KEY)
        # Повертаємо AUDIO модальність (необхідна для обробки голосу)
        # та вмикаємо обидва види транскрипції.
        # Видаляємо explicit_vad_signal, бо модель його не підтримує.
        self._config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=SYSTEM_INSTRUCTION,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
        )

    async def transcribe(self, audio_data: bytes, rms_val: float) -> str:
        if not audio_data:
            return ""

        print(f"DEBUG: Відправка {len(audio_data)} байт (Гучність RMS: {rms_val:.1f})")
        if rms_val < 10:
            print("⚠️  УВАГА: Дуже низький сигнал мікрофону. Можливо, Gemini нічого не почує.")

        input_text_parts: list[str] = []
        model_text_parts: list[str] = []
        
        try:
            # Напряму використовуємо WebSocket підключення
            async with self._client.aio.live.connect(model=MODEL, config=self._config) as session:
                if DEBUG_MODE:
                    print("DEBUG: WebSocket з'єднання встановлено.")

                async def send_audio():
                    try:
                        # Відправляємо все аудіо одним блоком і сигналізуємо про кінець.
                        await session.send_realtime_input(
                            audio={"data": audio_data, "mime_type": "audio/pcm"}
                        )
                        await session.send_realtime_input(audio_stream_end=True)
                    except Exception as e:
                        if DEBUG_MODE:
                            print(f"DEBUG: Помилка у send_audio: {e}")

                async def receive_responses():
                    try:
                        async for response in session.receive():
                            if DEBUG_MODE:
                                print(f"DEBUG API MSG: {response}")
                            
                            sc = response.server_content
                            if not sc: continue

                            # 1. Швидкий STT потік (сайд-кар)
                            if sc.input_transcription and sc.input_transcription.text:
                                input_text_parts.append(sc.input_transcription.text)
                            
                            # 2. Відповідь моделі (повільніше, але може бути точніше)
                            if sc.model_turn and sc.model_turn.parts:
                                for part in sc.model_turn.parts:
                                    if hasattr(part, "text") and part.text:
                                        if not getattr(part, "thought", False):
                                            model_text_parts.append(part.text)
                            
                            # Перевіряємо turn_complete для негайного завершення
                            if sc.turn_complete:
                                break
                    except Exception as e:
                        if DEBUG_MODE:
                            print(f"DEBUG: Помилка у receive_responses: {e}")

                # Запуск задач
                send_task = asyncio.create_task(send_audio())
                receive_task = asyncio.create_task(receive_responses())
                
                # Чекаємо завершення (STT зазвичай вкладається в 10-15 сек)
                await asyncio.wait([send_task, receive_task], timeout=20.0)

        except Exception as e:
            print(f"❌ Помилка Gemini API: {e}")
            return ""

        # Пріоритет на швидкість: якщо є input_transcription, беремо її
        # Вона приходить частинами, які Gemini вже розділив пробілами
        if input_text_parts:
            full_text = "".join(input_text_parts).strip()
        elif model_text_parts:
            # Якщо STT потік порожній, беремо результат моделі
            full_text = "".join(model_text_parts).strip()
        else:
            return ""
        if not full_text:
            return ""

        # Чистка від артефактів моделі
        import re
        # Видаляємо все в подвійних зірочках (залишки thoughts)
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

        # Розбиваємо на блоки і вибираємо останній (якщо модель повторила фразу після коментаря)
        # Або шукаємо блок, де є кирилиця
        blocks = [b.strip() for b in full_text.split("\n") if b.strip()]
        if not blocks: return ""
        
        # Пріоритет: останній блок, що містить кирилицю
        for block in reversed(blocks):
            if re.search(r'[а-яА-ЯіїєґІЇЄҐ]', block):
                # Прибираємо лапки, якщо модель їх додала
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

        # Обчислюємо RMS (гучність) для діагностики
        rms_val = self._recorder.get_rms(audio_data)

        # Запускаємо транскрипцію в asyncio event loop
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self._process(audio_data, rms_val), self._loop
            )
            # Не блокуємо потік хоткея — результат обробиться в _process
        else:
            print("⚠️  Event loop не запущено!")

    async def _process(self, audio_data: bytes, rms_val: float):
        """Транскрибує аудіо і вводить текст."""
        try:
            text = await self._transcriber.transcribe(audio_data, rms_val)
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
