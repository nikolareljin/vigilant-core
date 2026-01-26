# VigilantCore Documentation

Welcome to the VigilantCore documentation.

## Contents

| Document | Description |
|----------|-------------|
| [Installation Guide](installation.md) | How to install and run VigilantCore |
| [Configuration Guide](configuration.md) | All configuration options explained |
| [Features](features.md) | Complete feature documentation |
| [Examples](examples.md) | Real-world usage examples |

## Quick Links

- **Web Dashboard**: http://127.0.0.1:8765
- **Data View**: http://127.0.0.1:8765/data

## Getting Help

If you encounter issues:

1. Check the [Installation Guide](installation.md#troubleshooting) for common solutions
2. Ensure Ollama is running: `ollama serve`
3. Check process status: `./run.sh status`
4. View logs in your terminal

## Privacy

VigilantCore processes all data locally using Ollama. No data is sent to external AI services. API keys for NewsAPI, Google CSE, etc. are stored locally in your config directory and are only used to fetch public news data.
