# Java Performance Evolution (History) Buddy

## Overview
JPerfEvo is a comprehensive framework designed to analyze Java project performance over time by mining commit history, identifying relevant changes, and benchmarking them using JMH (Java Microbenchmark Harness). The tool offers insights into performance evolution and enables statistical significance testing of performance changes.

## Features
- Clone and analyze Java project repositories.
- Mine project changes and identify benchmark dependencies.
- Select candidate commits for benchmarking.
- Execute benchmarks using JMH.
- Analyze performance results for statistical significance.
- Optional integrations for kernel tracing, LLM services, email notifications, and database storage.

## Requirements
- Python 3.x
- Java Development Kit (JDK 8 or later)
- Git
- Docker and Docker Compose
- Additional Python dependencies (install via `requirements.txt`)

## Installation
1. Clone the JPerfEvo repository:
   ```bash
   git clone https://github.com/kavehshahedi/java-performance-history-buddy
   cd java-performance-history-buddy
   ```
2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure Java, Git, Docker, and Docker Compose are installed and configured on your system.

## Usage
### Command-Line Interface
The primary entry point is `main.py`. Use the following command to analyze a project:

```bash
python3 main.py \
  --name <project_name> \
  --git <git_url> \
  --package <package_name> \
  [optional arguments]
```

#### Required Arguments
- `--name`: Name of the project to analyze.
- `--git`: Git URL of the project repository.
- `--package`: Target Java package for analysis.

#### Optional Arguments
- `--benchmark-module`: Specify a custom benchmark module.
- `--custom-commits`: File path containing custom commit hashes (one per line).
- `--forks`: Number of forks for JMH benchmarking (default: 3).
- `--warmups`: Number of warmup iterations (default: 0).
- `--iterations`: Number of measurement iterations (default: 5).
- `--measurement-time`: Time per iteration in seconds (default: 10s).
- `--max-instrumentations`: Max instrumentations per method (default: 100,000).
- `--kernel`: Enable kernel tracing using LTTng.
- `--llm`: Enable LLM-based analysis.
- `--email`: Enable email notifications.
- `--use-db`: Use MongoDB for data storage.
- `--cloud-db`: Use MongoDB Atlas for cloud storage.

### Example
```bash
python3 main.py \
  --name SampleProject \
  --git https://github.com/sample/repository.git \
  --package com.sample.project \
  --benchmark-module benchmarks \
  --forks 5 \
  --iterations 10
```

## Docker Support
JPerfEvo includes Docker support for consistent and portable execution across platforms.

### Building the Docker Image
To build the Docker image for JPerfEvo, use the following commands. These commands ensure compatibility across platforms (e.g., Linux and Windows):

```bash
# Build the image for the current platform
docker build -t jphb:latest .

# For multi-platform support (e.g., Linux amd64 and Windows x86/x64):
docker buildx create --use
docker buildx build --platform linux/amd64,windows/amd64 -t jphb:latest . --push
```

### Running the Docker Container
Use `docker-compose.yml` for managing the container:

```bash
docker-compose up -d
```

This will start the container with the following features:
- Exposes port `80` for accessing results.
- Mounts volumes for results and project data.
- Supports configurable runtime commands through the `PROGRAM` environment variable.

### Example Environment Variables
In the `docker-compose.yml` file:
```yaml
services:
  jphb:
    image: jphb:latest
    container_name: jphb-container
    ports:
      - "80:80"
    volumes:
      - jphb_data:/app/results
      - jphb_projects:/app/projects
    environment:
      - PROGRAM=python main.py --name ExampleProject --git https://github.com/example/repo.git --package com.example.project
```

## Pipeline Workflow
1. **Clone Repository**: Clones the specified Git repository and validates it.
2. **Mine Changes**:
   - Identifies relevant commits with method changes.
   - Detects benchmark dependencies.
3. **Select Candidate Commits**:
   - Identifies commits suitable for benchmarking based on method changes and buildability.
4. **Benchmark Execution**:
   - Runs JMH benchmarks on candidate commits.
   - Collects execution time and traces for analysis.
5. **Performance Analysis**:
   - Compares results between commits using statistical significance tests (e.g., Mann-Whitney U, Cliff’s Delta).
   - Identifies performance regressions or improvements.

## Results
The tool generates the following outputs:
- Benchmark execution results and statistical significance reports.
- Candidate commit details and mined method changes.
- Trace data and analysis summaries.

## Optional Integrations
- **Kernel Tracing**: Enable tracing of system calls and interrupts using LTTng.
- **LLM Services**: Use AI to validate and enhance method changes.
- **Email Notifications**: Notify users of pipeline results via email.
- **Database Support**: Store results in MongoDB for further analysis.

## Citation
```bibtex
@inproceedings{shahedi2025jperfevo,
  title={JPerfEvo: A Tool for Tracking Method-Level Performance Changes in Java Projects},
  author={Shahedi, Kaveh and Lamothe, Maxime and Khomh, Foutse and Li, Heng},
  booktitle={2025 IEEE/ACM 22nd International Conference on Mining Software Repositories (MSR)},
  pages={856--860},
  year={2025},
  organization={IEEE}
}
```

## License
This project is licensed under the MIT License. See `LICENSE` for more details.
