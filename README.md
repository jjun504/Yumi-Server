# Yumi Server - Smart Assistant

Yumi, comprehensive AI-powered smart assistant with *customizable* voice interaction, smart home control, and multi-service integration capabilities.

This is basically the backend of Yumi. You can visit the client repository here: [Yumi Client](https://github.com/jjun504/Yumi-Client)

## Features

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

> **Important Note**: The GPT-SoVITS integration is implemented in the codebase but requires a self-hosted GPT-SoVITS server instance. Users need to set up their own GPT-SoVITS server and configure the appropriate API endpoints to use this feature.

### Communication Protocols
- **UDP + MQTT**: Device discovery and communication
- **WebSocket**: Real-time web interface communication

## Quick Start

### Prerequisites
- Python 3.8+
- Conda (recommended) or pip
- Windows/Linux/macOS

### Installation

1. **Create and activate virtual environment**
   ```bash
   conda create -n smart_assistant python=3.11
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

## Hardware Integration

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

## Contact

For questions, support, or collaboration opportunities, please reach out to us:

- **CHEN JUN XU**: [chen.jun.xu@student.mmu.edu.my](mailto:chen.jun.xu@student.mmu.edu.my)
- **GOH WEI TING**: [goh.wei.ting@student.mmu.edu.my](mailto:goh.wei.ting@student.mmu.edu.my)
- **LEE ZHENG WEI**: [lee.zheng.wei@student.mmu.edu.my](mailto:lee.zheng.wei@student.mmu.edu.my)

### **Institution**
**Multimedia University (MMU)**
Faculty of Information Science and Technology

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

**Third-party notices:**
- Wake word detection powered by [Porcupine](https://github.com/Picovoice/porcupine) (Picovoice) — subject to [Picovoice Terms of Use](https://picovoice.ai/docs/terms-of-use/)
- Music playback via [mpv](https://mpv.io/) and [yt-dlp](https://github.com/yt-dlp/yt-dlp)

## Contributing

Issues and Pull Requests are welcome to improve the project.
