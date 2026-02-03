Autonomous Refactoring Agent (ARA) 🤖
A Self-Correcting, Human-in-the-Loop Refactoring Engine powered by LangGraph & Gemini.

ARA is not just a code generator; it is a software engineering agent designed to modernize legacy Python codebases. It moves beyond simple "copilots" by implementing a cyclic "Plan-Execute-Verify-Reflect" architecture. It iteratively writes code, runs compilers/linters to detect errors, and self-corrects its own mistakes before asking for human approval.

🚀 Key Features
🧠 Cognitive Architecture: Uses the Reflexion Pattern to "think" about errors. If a refactor fails type checking, the agent analyzes the error log, plans a fix, and retries automatically.

🔄 Cyclic Self-Correction: Unlike linear chains, ARA uses a stateful graph (LangGraph) that loops until code passes all validation checks (Syntax, Ruff, Pyright) or hits a retry limit.

🛡️ Lossless Transformation: Integrates LibCST to ensure refactoring preserves comments, formatting, and project structure (no more "spaghetti code" from LLMs).

👨‍💻 Human-in-the-Loop (HITL): "Glass Box" design. The agent pauses at critical decision points, presenting a visual diff for your approval before committing any changes.

💾 Long-Running Persistence: Backed by PostgreSQL, allowing workflows to pause, resume, and survive server restarts without losing context.

🏗️ System Architecture
ARA operates as a 6-node state graph orchestrating the lifecycle of a code change:

Code snippet
graph TD
    User[User Input] --> Analyzer
    Analyzer[🔍 Analyzer Node] --> Generator
    Generator[📝 Generator Node] --> Validator
    Validator[✅ Validator Node] -->|Pass| HumanReview
    Validator -->|Fail| Reflector
    Reflector[🤔 Reflector Node] -->|Feedback Loop| Generator
    HumanReview[👤 Human Review] -->|Approve| Committer
    HumanReview -->|Reject| End
    Committer[💾 Committer Node] --> End[End]
Node Breakdown
Analyzer: Scans the codebase to identify refactoring targets and build a dependency graph.

Generator: Uses Gemini 2.0 Flash to generate improved code or LibCST scripts based on the goal.

Validator: The "System 2" critic. Runs Ruff (linting), Pyright (type checking), and Python compilation checks.

Reflector: Activates on failure. Reads error logs and creates a "critique" to guide the Generator's next attempt.

HumanReview: A persistent interrupt state that waits for user approval via the Web UI.

Committer: Finalizes the change (e.g., creates a PR or writes to disk).

🛠️ Technology Stack
Orchestration: LangGraph

LLM: Google Gemini 2.0 Flash

Backend: FastAPI

Frontend: HTML/JS (served via Python)

Database: PostgreSQL (via Docker)

Static Analysis: Ruff, Pyright, LibCST

⚡ Getting Started
Prerequisites
Python 3.11+

Docker & Docker Compose

Gemini API Key (Get one here)

1. Installation
Clone the repository and install dependencies:

Bash
git clone https://github.com/vasukochhar/ara.git
cd ara

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
2. Configuration
Create a .env file in the root directory:

Ini, TOML
GEMINI_API_KEY=your_actual_api_key_here
LLM_MODEL=gemini-2.0-flash
DATABASE_URL=postgresql://user:password@localhost:5432/ara_db
# Debugging flags
MOCK_LLM=false
3. Start the Infrastructure
Launch the PostgreSQL database container:

Bash
docker-compose up -d
4. Run the System
Start the Backend API:

Bash
uvicorn ara.api.main:app --host 127.0.0.1 --port 8000 --reload
Start the Frontend UI:

Bash
python -m http.server 3000 --directory frontend
Access the dashboard at: http://localhost:3000

📖 Usage Guide
Open the UI: Navigate to http://localhost:3000.

Submit a Task:

Code: Paste your legacy Python code.

Goal: Describe the change (e.g., "Convert this function to use Pydantic models and add docstrings").

Monitor Progress: Watch the agent move through the graph (Analyze -> Generate -> Validate).

Review Changes: If validation passes, a Diff View will appear.

Approve: Applies the changes.

Reject: Stops the workflow.

📂 Project Structure
Plaintext
src/ara/
├── api/            # FastAPI endpoints (main.py)
├── graph/          # LangGraph workflow definition (builder.py)
├── nodes/          # Core logic for each step
│   ├── analyzer.py
│   ├── generator.py
│   ├── validator.py
│   └── reflector.py
├── state/          # Pydantic state schemas
├── tools/          # File I/O and shell execution tools
├── persistence/    # DB checkpointing logic
└── provider.py     # LLM configuration
🛡️ Production Hardening
We have implemented several resilience features for real-world use:

✅ Rate Limit Handling: Exponential backoff retry logic (up to 10 retries) for Gemini API calls.

✅ Fallback Mode: Analyzer and Generator nodes can degrade gracefully if the LLM is temporarily unavailable.

✅ Validation Bypasses: Configurable flags to bypass strict checks during development/debugging.

✅ Robust Parsing: Regex-based extractors for handling malformed [SUMMARY] / [CODE] blocks from the LLM.

🤝 Contributing
Pull requests are welcome! For major changes, please open an issue first to discuss what you would like to change.

📄 License
MIT