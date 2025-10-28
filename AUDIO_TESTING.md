# Audio Services Testing Infrastructure

This document describes the comprehensive audio testing infrastructure created for June Agent's STT and TTS services.

## 🎯 Overview

We've created a complete testing framework that includes:
- **Data-driven tests** with real audio samples
- **Synthetic test cases** for consistent evaluation
- **Performance metrics** and quality assessment
- **Automated deployment** and testing scripts
- **Integration with health checks**

## 📁 Test Infrastructure Files

### Core Testing Scripts
- **`services/cli-tools/scripts/audio_test_suite.py`** - Comprehensive audio testing suite
- **`services/cli-tools/scripts/simple_audio_test.py`** - Simple audio service tester
- **`scripts/test_audio_services.sh`** - Shell-based audio testing script
- **`scripts/deploy_audio_services.sh`** - Deployment and testing automation

### Test Data Management
- **LibriSpeech test-clean dataset** - Real speech samples for STT testing
- **LJSpeech dataset** - High-quality speech samples for TTS testing
- **Synthetic test cases** - Generated test cases for consistent evaluation
- **Audio evaluation metrics** - WER, CER, MCD, MSE calculations

## 🧪 Test Categories

### STT (Speech-to-Text) Tests
**Test Cases:**
- "Hello, how are you today?"
- "The quick brown fox jumps over the lazy dog."
- "Artificial intelligence is transforming the world."
- "Please call me at 555-123-4567."
- "The weather is sunny with a temperature of 75 degrees."

**Metrics:**
- **Word Error Rate (WER)** - Percentage of words incorrectly transcribed
- **Character Error Rate (CER)** - Percentage of characters incorrectly transcribed
- **Processing Time** - Time taken to transcribe audio
- **Confidence Score** - Model confidence in transcription

### STT (Speech-to-Text) Tests
**Test Cases:**
- "Hello, how are you today?"
- "The quick brown fox jumps over the lazy dog."
- "Artificial intelligence is transforming the world."
- "Please call me at 555-123-4567."
- "The weather is sunny with a temperature of 75 degrees."

**Metrics:**
- **Word Error Rate (WER)** - Percentage of words incorrectly transcribed
- **Character Error Rate (CER)** - Percentage of characters incorrectly transcribed
- **Processing Time** - Time taken to transcribe audio
- **Confidence Score** - Model confidence in transcription

### Round-Trip Tests (TTS→STT)
**Concept:** Convert text to speech, then transcribe the audio back to text
**Purpose:** Validate integrated performance of both services working together

**Test Process:**
1. Input text is converted to speech using TTS service
2. Generated audio is transcribed using STT service
3. Original text is compared with transcribed result
4. Accuracy metrics are calculated

**Metrics:**
- **Exact Match Rate** - Percentage of exact matches
- **Word Error Rate (WER)** - Errors in transcription
- **Character Error Rate (CER)** - Character-level errors
- **Match Percentage** - Overall accuracy score
- **Processing Time** - Total TTS + STT time

**Success Criteria:**
- **Exact Match Rate:** ≥80% for quality validation
- **WER:** < 10% for integrated system
- **CER:** < 5% for integrated system

### TTS (Text-to-Speech) Tests
**Test Cases:**
- "Hello, this is a test of the text-to-speech system."
- "The quick brown fox jumps over the lazy dog."
- "Artificial intelligence and machine learning are fascinating topics."
- "Please speak clearly and at a moderate pace."
- "This is a test of different sentence lengths and complexity."

**Metrics:**
- **Mel Cepstral Distortion (MCD)** - Audio quality measurement
- **Mean Squared Error (MSE)** - Signal quality assessment
- **Processing Time** - Time taken to generate audio
- **Duration Accuracy** - Generated audio length vs expected

## 🚀 Usage Instructions

### Prerequisites
1. **Docker permissions** - User must be in docker group
2. **grpcurl** - For gRPC health checks
3. **Python3** - For advanced testing (optional)
4. **Audio libraries** - librosa, soundfile (for comprehensive tests)

### Quick Start
```bash
# Deploy and test STT/TTS services
./scripts/deploy_audio_services.sh

# Run tests only (if services are running)
./scripts/deploy_audio_services.sh --test-only

# Run comprehensive audio tests
./scripts/test_audio_services.sh

# Run round-trip tests only
python3 services/cli-tools/scripts/round_trip_test.py --test-cases 10

# Run health checks
./run_checks.sh
```

### Docker Permission Setup
```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Start new shell session
newgrp docker

# Or restart your session
```

### Manual Testing
```bash
# Check STT service health
grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check

# Check TTS service health
grpcurl -plaintext localhost:50053 grpc.health.v1.Health/Check

# Run Python-based tests
python3 services/cli-tools/scripts/simple_audio_test.py --test-all
```

## 📊 Test Results

### Expected Performance
**STT Service:**
- WER: < 5% for clear speech
- CER: < 2% for clear speech
- Processing Time: < 2x real-time
- Success Rate: > 95%

**TTS Service:**
- MCD: < 5.0 (lower is better)
- Processing Time: < 1x real-time
- Success Rate: > 95%
- Audio Quality: Clear and natural

### Test Reports
Test results are saved to:
- **`/home/rlee/june_data/audio_tests/`** - Test data and results
- **`audio_test_report_YYYYMMDD_HHMMSS.json`** - Timestamped reports
- **`stt_report.json`** - STT-specific results
- **`tts_report.json`** - TTS-specific results

## 🔧 Integration with Health Checks

The `run_checks.sh` script now includes:
- **Audio service health checks** - gRPC connectivity
- **Functionality tests** - Basic audio processing
- **Performance monitoring** - Response times and success rates
- **Test data validation** - Audio file availability

## 📈 Monitoring and Metrics

### Real-time Monitoring
- **Service health** - gRPC health checks
- **Response times** - Per-request timing
- **Success rates** - Test pass/fail ratios
- **Resource usage** - CPU, memory, GPU utilization

### Historical Analysis
- **Performance trends** - Over time analysis
- **Quality degradation** - Model performance tracking
- **Error patterns** - Common failure modes
- **Optimization opportunities** - Performance improvements

## 🛠️ Troubleshooting

### Common Issues
1. **Docker permission denied**
   - Solution: Add user to docker group
   - Command: `sudo usermod -aG docker $USER`

2. **grpcurl not found**
   - Solution: Install grpcurl
   - Command: `go install github.com/fullstorydev/grpcurl/cmd/grpcurl@latest`

3. **Services not responding**
   - Check: `docker compose ps`
   - Restart: `docker compose restart stt tts`

4. **Test failures**
   - Check logs: `docker compose logs stt tts`
   - Verify models: `python3 scripts/download_models.py --status`

### Debug Commands
```bash
# Check service status
docker compose ps stt tts nats

# View service logs
docker compose logs -f stt
docker compose logs -f tts

# Check model availability
python3 scripts/download_models.py --status

# Test individual services
grpcurl -plaintext localhost:50052 grpc.health.v1.Health/Check
grpcurl -plaintext localhost:50053 grpc.health.v1.Health/Check
```

## 🎯 Next Steps

1. **Resolve Docker permissions** - Add user to docker group
2. **Deploy services** - Run `./scripts/deploy_audio_services.sh`
3. **Run tests** - Execute comprehensive audio testing
4. **Monitor performance** - Use health checks and metrics
5. **Optimize models** - Based on test results and performance

## 📚 Additional Resources

- **AGENTS.md** - Development guidelines and best practices
- **README.md** - Project overview and setup instructions
- **run_checks.sh** - Comprehensive health check script
- **docker-compose.yml** - Service orchestration configuration

The audio testing infrastructure is now ready for deployment and comprehensive evaluation of STT and TTS services!
