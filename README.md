# Yumi Smart Assistant

A comprehensive AI-powered smart assistant system with voice interaction, smart home control, and multi-service integration capabilities.

## 🌟 Features

### Core Capabilities
- **Voice Interaction**: Wake word detection with real-time speech-to-text and text-to-speech
- **Smart Home Control**: Device management for lighting, climate, and media systems
- **AI Integration**: Multiple LLM, TTS, and STT service support
- **Music & Media**: YouTube integration with playlist management
- **Scheduling**: Time notifications and schedule management
- **Weather Integration**: Real-time weather updates and forecasts
- **Web Search**: Real-time information retrieval capabilities
- **Multi-User Support**: User authentication and device binding system

### AI Services Integration
- **Speech-to-Text (STT)**: Azure Speech Services
- **Text-to-Speech (TTS)**: Bytedance TTS, Azure TTS, GPT-SoVITS (Custom Voice)
- **Large Language Models (LLM)**: Groq, OpenAI, DeepSeek

> **⚠️ Important Note**: GPT-SoVITS (Custom Voice) TTS service is currently **not available for public use**. The GPT-SoVITS integration is implemented in the codebase but requires a self-hosted GPT-SoVITS server instance. Users need to set up their own GPT-SoVITS server and configure the appropriate API endpoints to use this feature.

### Communication Protocols
- **UDP + MQTT**: Device discovery and communication
- **WebSocket**: Real-time web interface communication
- **Event System**: Internal event-driven architecture

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Interface │    │  Voice Interface │    │  Smart Devices  │
│   (Flask/HTML)  │    │  (STT/TTS/Wake)  │    │   (MQTT/UDP)    │
└─────────┬───────┘    └─────────┬────────┘    └────────┬────────┘
          │                      │                      │
          └──────────────────────┼──────────────────────┘
                                 │
                    ┌────────────┴──────────────┐
                    │     Server Core           │
                    │  - Event System           │
                    │  - Device Manager         │
                    │  - Chat Processor         │
                    │  - Configuration Manager  │
                    └───────────────────────────┘
                                 │
          ┌──────────────────────┼──────────────────────┐
          │                      │                      │
┌─────────┴───────┐    ┌─────────┴───────┐    ┌─────────┴───────┐
│   AI Services   │    │   Data Storage  │    │  External APIs  │
│ - LLM Manager   │    │ - User Data     │    │ - Weather API   │
│ - TTS Manager   │    │ - Device Config │    │ - YouTube API   │
│ - STT Manager   │    │ - Chat History  │    │ - Web Search    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Conda (recommended) or pip
- Windows/Linux/macOS

### Installation

1. **Create and activate virtual environment**
   ```bash
   conda create -n smart_assistant python=3.8
   conda activate smart_assistant
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install libmpv (for audio playback)**
   - **Windows**: Download from [SourceForge](https://sourceforge.net/projects/mpv-player-windows/files/libmpv/)
     - Extract and copy `libmpv-2.dll` to `C:\Windows\System32`
   - **Linux**: `sudo apt-get install libmpv1`
   - **macOS**: `brew install mpv`

4. **Install opuslib (for audio encoding)**
   - **Windows**: Download Opus library from [Opus Downloads](https://opus-codec.org/downloads/)
     - Extract and copy `opus.dll` to `C:\Windows\System32`
     - Or install via conda: `conda install -c conda-forge opuslib`
   - **Linux**: `sudo apt-get install libopus-dev && pip install opuslib`
   - **macOS**: `brew install opus && pip install opuslib`

5. **Configure environment variables**
   ```bash
   # Create .env file with your API keys
   cp .env.example .env
   # Edit .env with your API keys
   ```

6. **Start the server**
   ```bash
   python server.py
   ```

7. **Access the web interface**
   - Open browser and navigate to `http://localhost:5000`
   - Create an account or login with existing credentials

## 🔌 Hardware Integration

### Supported Device Types
- **Lighting**: Smart bulbs, LED strips, switches
- **Climate**: Temperature sensors, fans, air conditioning
- **Media**: Speakers, displays, audio systems
- **Sensors**: Motion, temperature, humidity sensors

### Arduino Integration
The system includes Arduino sketches for various smart devices:
- `smart_device_ino/light.ino`: Smart lighting control
- `smart_device_ino/hanger.ino`: Smart clothes hanger
- `smart_device_ino/water_sensor.ino`: Water level monitoring
- `smart_device_ino/combined_airdrop_sensor_hanger.ino`: Multi-sensor device

### Communication Protocol
- **Discovery**: UDP broadcast on port 50000
- **Control**: MQTT with topic prefix `smart187`
- **Status**: Real-time status updates via MQTT
- **Audio**: PCM audio streaming for voice interaction

## 🚨 Troubleshooting

### Common Issues

#### Server Won't Start
```bash
# Check port availability
netstat -an | grep :5000

# Check Python environment
python --version
pip list | grep flask

# Check configuration
python -c "from unified_config import unified_config; print('Config OK')"
```

#### Device Discovery Issues
```bash
# Check UDP port
netstat -an | grep :50000

# Test MQTT connection
python -c "import paho.mqtt.client as mqtt; print('MQTT OK')"

# Check device configuration
ls device_configs/
```

#### AI Service Errors
```bash
# Test API keys
python -c "from groqapi import GroqChatModule; print('Groq OK')"
python -c "from azureTTS import TTSManager; print('Azure OK')"

# Check service configuration
grep -r "api_key" config/
```

#### Audio Issues
```bash
# Check libmpv installation
python -c "import mpv; print('MPV OK')"

# Test audio devices
python -c "import sounddevice; print(sounddevice.query_devices())"

# Check audio files
ls sound/
```

### Log Analysis
```bash
# View recent server logs
tail -f Log/Server_System_Log/system.log

# Check device logs
tail -f device_configs/*/system.log

# Monitor chat processing
tail -f logs/stt_stream_bridge_processor.log
```

### Performance Optimization
- **Memory Usage**: Monitor Python process memory consumption
- **CPU Usage**: Check for high CPU usage during AI processing
- **Network Latency**: Optimize MQTT broker selection
- **Storage**: Regular cleanup of old chat history and logs

## Team Members

This project was developed by:

| Student ID | Name | Role |
|------------|------|------|
| 1221206572 | CHEN JUN XU | Project Lead & Main Developer |
| 1221208439 | GOH WEI TING | Developer |
| 1221208146 | LEE ZHENG WEI | Developer |

## Contact

For questions, support, or collaboration opportunities, please reach out to us:

### 📧 **Primary Contact**
- **Email**: [1221206572@student.mmu.edu.my](mailto:1221206572@student.mmu.edu.my)
- **Phone**: +60 11-577 68208

### 👥 **Team Contact**
- **CHEN JUN XU**: [1221206572@student.mmu.edu.my](mailto:1221206572@student.mmu.edu.my)
- **GOH WEI TING**: [1221208439@student.mmu.edu.my](mailto:1221208439@student.mmu.edu.my)
- **LEE ZHENG WEI**: [1221208146@student.mmu.edu.my](mailto:1221208146@student.mmu.edu.my)

### 🏫 **Institution**
**Multimedia University (MMU)**
Faculty of Information Science and Technology

---

*© 2025 Yumi Team. All rights reserved.*