# June Agent Documentation

Welcome to the comprehensive documentation for June Agent, an interactive autonomous agent system built with microservices architecture.

## 📚 Documentation Overview

This documentation is organized by audience and purpose to help you find what you need quickly.

### For Users
- **[User Guide](guides/USER_GUIDE.md)** - Getting started, Telegram bot guide, Discord bot guide, configuration guide, and feature documentation
- **[Troubleshooting Guide](guides/TROUBLESHOOTING.md)** - Common issues, service-specific troubleshooting, error reference, performance issues, and debugging procedures

### For Developers
- **[Development Setup](guides/DEVELOPMENT.md)** - Development environment setup, project structure, workflow, code quality standards, testing guide, building/packaging, and contributing guidelines
- **[Agent Development Guide](guides/AGENTS.md)** - Essential information for AI agents working on the June Agent project, including architecture details, development practices, and environment specifics
- **[Contributing Guidelines](guides/CONTRIBUTING.md)** - How to contribute to the project, code review process, and issue reporting

### For Operators
- **[Operational Readiness Checklist](OPERATIONAL_READINESS.md)** - Comprehensive checklist for operational tasks, prerequisites, steps, and troubleshooting
- **[Deployment Guides](guides/DEPLOYMENT.md)** - Local development, production, cloud deployments (AWS/GCP/Azure), single/multi-node setups, configuration, SSL/TLS, backup/recovery, and monitoring
- **[TensorRT-LLM Setup Guide](guides/TENSORRT_LLM_SETUP.md)** - TensorRT-LLM migration, model repository setup, model compilation, and management
- **[NIM Setup Guide](guides/NIM_SETUP.md)** - NVIDIA NIM (NVIDIA Inference Microservice) setup, image name verification, NGC API key configuration, and troubleshooting
- **[Riva NIM Deployment Guide](guides/RIVA_NIM_DEPLOYMENT.md)** - Complete step-by-step workflow for deploying Riva ASR/TTS NIM containers, integrating helper scripts and tools
- **[Agent Communication Guide](guides/AGENT_COMMUNICATION.md)** - Direct agent-to-user communication system for whitelisted users, service conflict prevention, message syncing, and polling
- **[Architecture Documentation](architecture/ARCHITECTURE.md)** - System architecture, service architecture, data flow diagrams, infrastructure components, network architecture, security, scalability, and design decisions
- **[Agentic Capabilities](architecture/AGENTIC_CAPABILITIES.md)** - Comprehensive documentation for June's agentic capabilities system, enabling autonomous AI agents to discover, plan, execute, and verify tasks

### For API Users
- **[API Documentation](API/)** - Complete API docs for LLM Inference (TensorRT-LLM gRPC, default), STT/TTS services (gRPC), Telegram Bot API, Discord Bot API, and TODO MCP Service with examples

## 🗂️ Documentation Structure

```
docs/
├── README.md                    # This file - documentation index
├── API/                         # API documentation
│   ├── gateway.md.obsolete      # Gateway REST/WebSocket API (archived - service removed)
│   ├── inference.md            # Inference API gRPC
│   ├── stt.md                  # STT Service gRPC
│   ├── tts.md                  # TTS Service gRPC
│   ├── telegram.md             # Telegram Bot API
│   ├── discord.md              # Discord Bot API
│   └── todo-mcp.md             # TODO MCP Service API
├── guides/                      # User and developer guides
│   ├── USER_GUIDE.md           # User-facing documentation
│   ├── DEPLOYMENT.md           # Deployment guides
│   ├── DEVELOPMENT.md          # Development setup and workflow
│   ├── CONTRIBUTING.md         # Contributing guidelines
│   ├── TROUBLESHOOTING.md      # Troubleshooting guide
│   ├── AGENTS.md               # Agent development guide
│   ├── AUDIO_TESTING.md        # Audio services testing
│   ├── TENSORRT_LLM_SETUP.md   # TensorRT-LLM setup and migration guide
│   ├── NIM_SETUP.md            # NVIDIA NIM setup guide
│   ├── RIVA_NIM_DEPLOYMENT.md  # Riva ASR/TTS NIM deployment guide
│   ├── AGENT_COMMUNICATION.md  # Direct agent-to-user communication guide
│   └── FIXES_APPLIED.md        # Fixes and improvements log
└── architecture/                # Architecture documentation
    ├── ARCHITECTURE.md          # System architecture overview
    └── AGENTIC_CAPABILITIES.md  # Agentic capabilities system
```

## 🚀 Quick Links

### Getting Started
- [Quick Start Guide](../README.md#-quick-start) - Get June running in minutes
- [Development Setup](guides/DEVELOPMENT.md) - Set up your development environment
- [User Guide](guides/USER_GUIDE.md) - Learn how to use June

### Common Tasks
- [Deploy to Production](guides/DEPLOYMENT.md) - Production deployment guide
- [Troubleshooting](guides/TROUBLESHOOTING.md) - Fix common issues
- [API Reference](API/) - Complete API documentation
- [Architecture Overview](architecture/ARCHITECTURE.md) - Understand the system

### For Contributors
- [Contributing Guidelines](guides/CONTRIBUTING.md) - How to contribute
- [Development Workflow](guides/DEVELOPMENT.md#development-workflow) - Development process
- [Agent Development](guides/AGENTS.md) - Guidelines for AI agents

## 📖 Documentation by Topic

### Architecture & Design
- [System Architecture](architecture/ARCHITECTURE.md) - High-level system design
- [Agentic Capabilities](architecture/AGENTIC_CAPABILITIES.md) - Autonomous agent system
- [Service Architecture](../README.md#-architecture-overview) - Core services overview

### Development
- [Development Setup](guides/DEVELOPMENT.md) - Environment setup
- [Agent Development](guides/AGENTS.md) - AI agent guidelines
- [Testing Guide](guides/DEVELOPMENT.md#testing-guide) - Testing procedures
- [Audio Testing](guides/AUDIO_TESTING.md) - Audio services testing

### Operations
- [Deployment](guides/DEPLOYMENT.md) - Deployment procedures
- [TensorRT-LLM Setup](guides/TENSORRT_LLM_SETUP.md) - TensorRT-LLM migration and setup
- [NIM Setup](guides/NIM_SETUP.md) - NVIDIA NIM setup and configuration
- [Riva NIM Deployment](guides/RIVA_NIM_DEPLOYMENT.md) - Complete workflow for deploying Riva ASR/TTS NIMs
- [Agent Communication](guides/AGENT_COMMUNICATION.md) - Direct agent-to-user communication system
- [Troubleshooting](guides/TROUBLESHOOTING.md) - Common issues and solutions
- [Monitoring](../README.md#-monitoring) - Metrics and observability

### APIs
- [Inference API](API/inference.md) - LLM gRPC service
- [STT/TTS APIs](API/) - Speech services
- [Telegram Bot API](API/telegram.md) - Telegram bot integration
- [Discord Bot API](API/discord.md) - Discord bot integration

## 🔍 Finding Documentation

### By Role
- **End User**: Start with [User Guide](guides/USER_GUIDE.md)
- **Developer**: Start with [Development Setup](guides/DEVELOPMENT.md)
- **Operator**: Start with [Deployment Guide](guides/DEPLOYMENT.md)
- **API User**: Start with [API Documentation](API/)

### By Task
- **Setting up June**: [Quick Start](../README.md#-quick-start)
- **Deploying to production**: [Deployment Guide](guides/DEPLOYMENT.md)
- **Using the API**: [API Documentation](API/)
- **Troubleshooting issues**: [Troubleshooting Guide](guides/TROUBLESHOOTING.md)
- **Contributing code**: [Contributing Guidelines](guides/CONTRIBUTING.md)
- **Understanding architecture**: [Architecture Documentation](architecture/ARCHITECTURE.md)

## 📝 Documentation Status

### Complete Documentation
- ✅ Architecture overview (in main README)
- ✅ Agent development guide
- ✅ Agentic capabilities system
- ✅ Audio testing infrastructure
- ✅ Quick start and basic usage

### In Progress
- 🚧 Comprehensive architecture documentation
- 🚧 Complete API documentation
- 🚧 User guides and manuals
- 🚧 Deployment guides
- 🚧 Troubleshooting guide
- 🚧 Development setup guide

### Planned
- 📋 Contributing guidelines
- 📋 Operational runbooks
- 📋 Performance tuning guide
- 📋 Security best practices

## 🔗 External Resources

- **Main README**: [../README.md](../README.md) - Project overview and quick start
- **GitHub Repository**: [https://github.com/rl337/june](https://github.com/rl337/june)
- **Issue Tracker**: GitHub Issues for bug reports and feature requests

## 📞 Getting Help

- **Documentation Issues**: If you find errors or missing information, please open an issue
- **Questions**: Check the [Troubleshooting Guide](guides/TROUBLESHOOTING.md) first
- **Contributions**: See [Contributing Guidelines](guides/CONTRIBUTING.md)

---

**Last Updated**: 2025-11-18  
**Documentation Version**: 1.0.0
