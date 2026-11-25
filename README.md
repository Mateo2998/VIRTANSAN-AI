# VIRTANSANLARA AI
### AI-Powered Enterprise Helpdesk and Workflow Automation System

## 1. Project Overview

VIRTANSANLARA AI is an AI-powered IT helpdesk system designed to assist employees with common company-related IT problems.

It uses Artificial Intelligence and Retrieval-Augmented Generation (RAG) to provide troubleshooting assistance using an internal knowledge base.

The system also provides employee account management, support ticket submission, human support requests, and an administrative dashboard.

## 2. Technologies Used

- Python 3.13
- FastAPI
- HTML, CSS, and JavaScript
- ChromaDB
- Ollama
- Qwen2.5 7B
- Nomic Embed Text
- Git and GitHub

## 3. System Requirements

- Windows 10 or Windows 11
- Python 3.13
- Ollama
- Visual Studio Code or another code editor
- At least 8 GB RAM recommended
- Internet connection for initial setup and downloads

## 4. AI Models

The project uses the following locally hosted models through Ollama:

- Qwen2.5 7B - Generates AI responses.
- Nomic Embed Text - Generates embeddings for knowledge retrieval.

Download the models using:

```powershell
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

## 5. Installation and Setup

Step 1. Install Python and Ollama.

Install Python 3.13 and Ollama on your computer.

Step 2. Open the project folder.

Open the VIRTANSANLARA AI project folder in Visual Studio Code.

Step 3. Create a virtual environment.

```powershell
py -3.13 -m venv .venv313
```

Step 4. Activate the virtual environment.

```powershell
.\.venv313\Scripts\Activate.ps1
```

Step 5. Install project dependencies.

If the project contains a requirements.txt file, run:

```powershell
pip install -r requirements.txt
```

Step 6. Start Ollama.

Make sure Ollama is running and both required models are installed.

If necessary, open another terminal and run:

```powershell
ollama serve
```

Step 7. Prepare the knowledge base.

Make sure the knowledge folder contains the required .txt documentation files.

Run the ingestion script:

```powershell
python ingest.py
```

This processes the knowledge documents and stores their embeddings in ChromaDB.

## 6. Running the Application

Activate the virtual environment and run:

```powershell
python -m uvicorn main:app --reload
```

Open your browser and visit:

http://127.0.0.1:8000

The application should now be accessible locally.

## 7. Main Features

- AI-powered IT helpdesk.
- Level 1 IT troubleshooting.
- Knowledge retrieval using RAG.
- Employee authentication.
- Password reset requests.
- Support ticket submission and tracking.
- Human support requests.
- Employee dashboard.
- Administrative dashboard.
- AI security and response guidelines.

## 8. Project Structure

```text
VIRTANSANLARA AI/
│
├── frontend/
│   └── index.html
│
├── knowledge/
│   ├── company_info.txt
│   ├── format_guidelines.txt
│   ├── password_reset.txt
│   ├── network_troubleshooting.txt
│   └── other IT documentation
│
├── main.py
├── ingest.py
├── requirements.txt
├── .gitignore
└── chroma_data/
```

Note: Additional frontend files and application data may be present depending on the current project version. ChromaDB data is generated during knowledge ingestion.

## 9. Troubleshooting

Ollama Connection Error:

Make sure Ollama is running before starting the application.

Missing Python Module:

Activate the virtual environment and install the required dependencies.

Knowledge Retrieval Problems:

Check the knowledge folder and run the ingestion script again.

AI Model Not Found:

Check installed models using:

```powershell
ollama list
```

## 10. Developers

Project Name: VIRTANSANLARA AI

Organization: VIRTANSANLARA

Course: Applied Generative AI for IT Solution Development

Project Type: AI-Powered Enterprise Helpdesk and Workflow Automation System

## 11. License

Developed as an academic project for Applied Generative AI for IT Solution Development.

## 12. AI Assistance Disclosure

Artificial Intelligence tools were used throughout the development of this project to assist with planning, programming, debugging, troubleshooting, documentation, and the creation of this README.

AI assistance was used as a development aid. The developers remain responsible for reviewing, testing, understanding, and verifying the implemented features and final project outputs.
