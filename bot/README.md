# 🤖 Yandex Station Mini 3 — Ultimate Telegram Control Bot, Intercom, Dialog History & PC Guard (v2.2)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Platform Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg)]()
[![Yandex Station Mini 3](https://img.shields.io/badge/device-Yandex%20Station%20Mini%203-red.svg)]()

> A feature-packed remote control Telegram bot for **Yandex Station Mini 3** with two-way voice walkie-talkie intercom, full conversation history by dates, room surveillance listening, PC Anti-Theft Guard, customizable RGB ring animations, 7-segment clock display text/faces, meme soundboard, real-time Text-to-Speech (TTS), live countdown alarm timer, and emergency loud siren.

🇷🇺 **Полная инструкция на русском языке:** Читайте [INSTRUCTION_RU.md](INSTRUCTION_RU.md)

---

## ✨ Key Features

* **💬 Full Conversation / Dialog History:**
  * Interactive date browser (`09.10.26`, `24.10.26`, `25.10.26`...).
  * View every question asked and Alice's response with timestamps `[HH:MM:SS]`.
  * Background real-time log watcher parsing hardware spotter and uniproxy directives.
* **🎙️ Two-Way Voice Intercom (Walkie-Talkie):**
  * Send voice notes or circles from Telegram -> speaker plays aloud in the room -> records 5s room reply and sends back as a voice message.
* **🛡️ PC Anti-Theft Guard (`/guard`):**
  * Protects your PC while you are away; triggers siren, strobe, and Telegram alerts on mouse move or keypress.
* **👂 Remote Room Listening (`/listen`):**
  * Hardware PDM microphone capture (from 3 to 30 seconds) delivered straight to Telegram.
* **🌈 Dynamic Top RGB Ring Lighting:**
  * Rainbow, Breathe, Spin, Police Strobe, White Flash.
  * 8 static quick colors (Red, Green, Blue, Purple, Orange, Cyan, Pink, White).
  * Auto State Restoration after notifications.
* **⏰ 7-Segment LED Clock Screen:**
  * Custom words & numbers (`1337`, `COOL`, `2026`, `HELP`).
  * Emoticons & faces: Cat `(=^.^=)`, Happy `(^_^)`, `(uwu)`.
  * ALS bypass for permanent 100% brightness or 10% night mode.
* **🔊 Built-in Meme Soundboard:**
  * Bruh, Vine Boom, Metal Pipe, Discord Ping, Fart Reverb, Win XP, Win Error, Rickroll, What?!, MLG Airhorn, Loud Siren.
* **🗣️ Real-time Voice Synthesis (TTS):**
  * Send `/say <message>` — speaker speaks aloud instantly in clear Russian.
* **⏱️ Countdown Timer & Alarm:**
  * `/alarm 10m` displays a real-time countdown on the physical clock face ending with an alarm siren.
* **🚨 Emergency Loud Siren Mode:**
  * High-volume alarm siren + police strobe + `ALRM` screen indicator.
* **⚡ System Info & Diagnostics:**
  * Full `fastfetch` system summary, disk usage, and remote reboot button.
* **🥷 100% Silent Background Operation:**
  * Runs invisibly via `pythonw.exe` without opening any console windows.
  * Integrated Windows startup autostart manager.

---

## 🚀 Quick Setup (2 Minutes)

1. **Extract or clone** this repository.
2. Run **`setup_bot.py`**:
   ```cmd
   python setup_bot.py
   ```
3. Follow the guided prompts:
   * Enter your speaker's IP address (default: `192.168.0.100`).
   * Enter your Telegram Bot Token (from [@BotFather](https://t.me/BotFather)).
   * Enter your Telegram User ID (from [@userinfobot](https://t.me/userinfobot)) for admin protection.
   * Enable silent autostart on Windows boot if desired.
4. **Done!** Open your bot in Telegram and start controlling your speaker!

---

## 🛠️ Management Scripts

* **`setup_bot.py`** — Interactive setup & installer wizard.
* **`manage_bot.py`** — Start / Stop / Check status of the silent background bot daemon.
* **`manage_autostart.py`** — Enable or disable Windows boot autostart with 1 click.
* **`run_bot.py`** — Run in interactive console mode (useful for debugging).
* **`pc_soundboard.py`** — Numpad hotkey listener for PC gaming / streaming.

---

## 📱 Bot Commands

| Command | Action |
|---|---|
| `/start` | Open interactive main menu with buttons |
| `/say <text>` | Speak custom text aloud via TTS |
| `/sound <name>` | Play sound (`bruh`, `boom`, `pipe`, `discord`, `fart`, `winxp`, `airhorn`, `rickroll`, `siren`) |
| `/alarm <time>` | Start timer with live display countdown (e.g. `/alarm 5m` or `/alarm 30s`) |
| `/screen <text>` | Display word on clock screen (up to 4 chars) |
| `/siren` | Trigger emergency loud siren mode |
| `/stop` | Stop all active audio, siren, and timers |

---

## 🔒 Security

All commands and button callbacks are restricted to the configured `admin_id`. Unauthorized users attempting to interact with the bot will be blocked.

---

## 📄 License
MIT License. Created for the Yandex Station Mini 3 enthusiast community.
