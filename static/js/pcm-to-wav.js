/**
 * PCM to WAV Converter
 * 
 * 这个工具用于将PCM格式的音频数据转换为WAV格式，使浏览器能够播放。
 * 支持从文件或二进制数据进行转换。
 */

class PCMConverter {
  /**
   * 从PCM文件路径创建可播放的音频元素
   * @param {string} pcmPath - PCM文件的路径
   * @param {number} sampleRate - 采样率，默认为24000
   * @param {number} numChannels - 声道数，默认为1（单声道）
   * @param {number} bitsPerSample - 位深度，默认为16位
   * @returns {Promise<HTMLAudioElement>} - 返回一个包含音频的audio元素
   */
  static async createAudioElementFromPCMFile(pcmPath, sampleRate = 24000, numChannels = 1, bitsPerSample = 16) {
    try {
      const response = await fetch(pcmPath);
      if (!response.ok) {
        throw new Error(`Failed to fetch PCM file: ${response.statusText}`);
      }
      
      const arrayBuffer = await response.arrayBuffer();
      return this.createAudioElementFromArrayBuffer(arrayBuffer, sampleRate, numChannels, bitsPerSample);
    } catch (error) {
      console.error('Error loading PCM file:', error);
      return this._createErrorAudio();
    }
  }

  /**
   * 从ArrayBuffer创建可播放的音频元素
   * @param {ArrayBuffer} pcmData - PCM音频数据
   * @param {number} sampleRate - 采样率，默认为24000
   * @param {number} numChannels - 声道数，默认为1（单声道）
   * @param {number} bitsPerSample - 位深度，默认为16位
   * @returns {HTMLAudioElement} - 返回一个包含音频的audio元素
   */
  static createAudioElementFromArrayBuffer(pcmData, sampleRate = 24000, numChannels = 1, bitsPerSample = 16) {
    try {
      const wavBlob = this.createWAVBlob(pcmData, sampleRate, numChannels, bitsPerSample);
      const audioURL = URL.createObjectURL(wavBlob);
      
      const audioElement = document.createElement('audio');
      audioElement.src = audioURL;
      audioElement.controls = true;
      
      // 当不再需要时释放URL资源
      audioElement.onended = () => {
        URL.revokeObjectURL(audioURL);
      };
      
      return audioElement;
    } catch (error) {
      console.error('Error creating audio element:', error);
      return this._createErrorAudio();
    }
  }

  /**
   * 从Base64编码的PCM数据创建可播放的音频元素
   * @param {string} base64PCM - Base64编码的PCM数据
   * @param {number} sampleRate - 采样率，默认为24000
   * @param {number} numChannels - 声道数，默认为1（单声道）
   * @param {number} bitsPerSample - 位深度，默认为16位
   * @returns {HTMLAudioElement} - 返回一个包含音频的audio元素
   */
  static createAudioElementFromBase64(base64PCM, sampleRate = 24000, numChannels = 1, bitsPerSample = 16) {
    try {
      const pcmData = this.base64ToArrayBuffer(base64PCM);
      return this.createAudioElementFromArrayBuffer(pcmData, sampleRate, numChannels, bitsPerSample);
    } catch (error) {
      console.error('Error processing Base64 PCM:', error);
      return this._createErrorAudio();
    }
  }

  /**
   * 将PCM数据转换为WAV Blob
   * @param {ArrayBuffer} pcmData - PCM音频数据
   * @param {number} sampleRate - 采样率
   * @param {number} numChannels - 声道数
   * @param {number} bitsPerSample - 位深度
   * @returns {Blob} - 返回WAV格式的Blob对象
   */
  static createWAVBlob(pcmData, sampleRate, numChannels, bitsPerSample) {
    const wavHeader = this.createWAVHeader(
      sampleRate,
      numChannels,
      bitsPerSample,
      pcmData.byteLength
    );

    const wavBuffer = new Uint8Array(wavHeader.byteLength + pcmData.byteLength);
    wavBuffer.set(new Uint8Array(wavHeader), 0);
    wavBuffer.set(new Uint8Array(pcmData), wavHeader.byteLength);

    return new Blob([wavBuffer], { type: 'audio/wav' });
  }

  /**
   * 创建WAV文件头
   * @param {number} sampleRate - 采样率
   * @param {number} numChannels - 声道数
   * @param {number} bitsPerSample - 位深度
   * @param {number} dataLength - 音频数据长度
   * @returns {ArrayBuffer} - 返回WAV头部数据
   */
  static createWAVHeader(sampleRate, numChannels, bitsPerSample, dataLength) {
    const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
    const blockAlign = (numChannels * bitsPerSample) / 8;
    const buffer = new ArrayBuffer(44);
    const view = new DataView(buffer);

    // 写入文本到DataView
    const writeString = (view, offset, text) => {
      for (let i = 0; i < text.length; i++) {
        view.setUint8(offset + i, text.charCodeAt(i));
      }
    };

    // RIFF标识符
    writeString(view, 0, 'RIFF');
    // 文件长度
    view.setUint32(4, 36 + dataLength, true);
    // WAVE标识符
    writeString(view, 8, 'WAVE');
    
    // fmt子块标识符
    writeString(view, 12, 'fmt ');
    // 子块1大小，固定为16
    view.setUint32(16, 16, true);
    // 音频格式，PCM为1
    view.setUint16(20, 1, true);
    // 声道数
    view.setUint16(22, numChannels, true);
    // 采样率
    view.setUint32(24, sampleRate, true);
    // 字节率 = 采样率 * 声道数 * 采样位数 / 8
    view.setUint32(28, byteRate, true);
    // 块对齐 = 声道数 * 采样位数 / 8
    view.setUint16(32, blockAlign, true);
    // 采样位数
    view.setUint16(34, bitsPerSample, true);

    // data子块标识符
    writeString(view, 36, 'data');
    // 音频数据长度
    view.setUint32(40, dataLength, true);

    return buffer;
  }

  /**
   * 将Base64编码转换为ArrayBuffer
   * @param {string} base64 - Base64编码的字符串
   * @returns {ArrayBuffer} - 返回解码后的ArrayBuffer
   */
  static base64ToArrayBuffer(base64) {
    // 移除Base64 URL安全格式中可能存在的填充字符和其他格式化字符
    base64 = base64.replace(/^data:audio\/[^;]+;base64,/, '');
    base64 = base64.replace(/\s/g, '');
    
    try {
      const binaryString = atob(base64);
      const length = binaryString.length;
      const bytes = new Uint8Array(length);

      for (let i = 0; i < length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
      }
      
      return bytes.buffer;
    } catch (e) {
      console.error('Base64 decoding error:', e);
      throw new Error('Invalid Base64 string');
    }
  }

  /**
   * 从PCM音频URL获取音频播放URL
   * @param {string} pcmUrl - PCM音频的URL
   * @param {Object} options - 配置选项
   * @returns {Promise<string>} - 返回可播放的音频URL
   */
  static async getPCMAudioURL(pcmUrl, options = {}) {
    const { sampleRate = 24000, numChannels = 1, bitsPerSample = 16 } = options;
    
    try {
      const response = await fetch(pcmUrl);
      if (!response.ok) throw new Error(`Failed to fetch PCM file: ${response.statusText}`);
      
      const arrayBuffer = await response.arrayBuffer();
      const wavBlob = this.createWAVBlob(arrayBuffer, sampleRate, numChannels, bitsPerSample);
      
      return URL.createObjectURL(wavBlob);
    } catch (error) {
      console.error('Error converting PCM to audio URL:', error);
      return '';
    }
  }

  /**
   * 创建错误提示的音频元素
   * @returns {HTMLAudioElement} - 返回一个显示错误的audio元素
   * @private
   */
  static _createErrorAudio() {
    const audioElement = document.createElement('audio');
    audioElement.controls = true;
    audioElement.style.display = 'none'; // 隐藏无法播放的元素
    
    const errorMessage = document.createElement('span');
    errorMessage.textContent = '无法加载音频';
    errorMessage.style.color = '#ff5252';
    errorMessage.style.fontSize = '0.8rem';
    
    const container = document.createElement('div');
    container.appendChild(errorMessage);
    container.appendChild(audioElement);
    
    // 返回音频元素，但实际显示会被错误消息替代
    return audioElement;
  }
}

// 导出PCMConverter类
if (typeof module !== 'undefined' && typeof module.exports !== 'undefined') {
  module.exports = PCMConverter;
} else {
  window.PCMConverter = PCMConverter;
}