
# Autonomous AI Travel Agent with Self-Correction

An AI travel agent built with a Microservices Architecture using React (Nginx) for the frontend and FastAPI for the backend. Orchestrated by LangGraph, this system features a cyclical multi-agent workflow powered by Groq (Llama 3) and Tavily.

It demonstrates a stateful, self-correcting AI system that can plan, research, evaluate, and generate detailed travel itineraries with interactive maps based on a single natural language request. The entire application is containerized with Docker.

---

## Overview

This project automates the travel planning process through a **cloud-native, microservices-based architecture**. The application is split into two fully containerized services: a **React frontend served by high-performance Nginx**, and a **FastAPI backend** that orchestrates a team of specialized AI agents.

A user interacts with the web interface to submit a high-level request (e.g., "a 5-day trip from Antalya to Rome for 2 people with a €2000 budget"). The request is processed by the backend container, which leverages **LangGraph** to manage stateful agents. These agents connect to live APIs for flight and hotel data, use real-time web search for activities, and autonomously self-correct to ensure the plan fits the user's constraints.

The core of this project is its **robust, scalable design**, utilizing **Docker** for orchestration and ensuring compatibility with enterprise cloud platforms like **Red Hat OpenShift**.

---

## Features

- **Microservices Architecture:** Fully containerized Frontend (React/Nginx) and Backend (FastAPI/Python) services, orchestrated via Docker Compose.
- **Interactive Web Interface:** A user-friendly UI to submit travel requests and view rich, markdown-formatted itineraries with embedded interactive maps.
- **Autonomous Multi-Agent System:** Uses LangGraph to manage a team of specialized agents (Planner, Researcher, Flight/Hotel/Event Specialists, Evaluator) that collaborate to achieve a complex goal.
- **Live API Integration:** Connects to real-time APIs for flights and hotels, and uses live web search (Tavily) for activities, grounding all plans in current, real-world data.
- **Intelligent Self-Correction:** A built-in Evaluator Agent critiques the generated plan against user constraints (budget, dates). If the plan fails (e.g., over budget), it triggers a targeted refinement loop to optimize flight or hotel choices.
- **Parallel Execution:** Performs concurrent searches for flights, hotels, and events to minimize latency.
- **Real-Time Data Integration:**

  - **Flights & Hotels:** Live data via Booking.com API (RapidAPI).

  - **Events:** Real-time concerts and events via Ticketmaster API.

  - **Activities:** Web-scale search for local attractions via Tavily API.
- **Cloud-Ready & Secure:** Designed with non-root user security policies (OpenShift compatible) and environment variable injection for secure credential management.
- **Rich Deliverables:** Generates a comprehensive Markdown report and an interactive HTML map (folium), accessible both via the UI and local volume mapping.

---

## Backend Workflow & Agentic Logic

The system is modeled as a stateful graph (`StateGraph`) in LangGraph. Each node represents an agent or a specific function, and edges define the flow of information and control.


### Backend Workflow

While the system architecture is microservices-based, the internal AI logic follows a strictly orchestrated LangGraph workflow running inside the Backend Container:

1. **Planner Agent:** Parses the user's natural language request into a structured `TripRequest` object containing all key constraints (destination, dates, budget, etc.).

2. **Parallel Initial Data Gathering (Flight, Hotel & Event Agents):** The system simultaneously initiates three independent searches for flights, hotels, and live events, significantly speeding up the data collection phase.

3. **Data Aggregator:** Acts as a synchronization barrier, waiting for all three parallel searches to complete before proceeding.

4. **Sequential Enrichment Pipeline:** To ensure data integrity, the following steps are performed in sequence:

   - **Activity Extraction Agent:** Scans the web with Tavily to find relevant points of interest.

   - **Geocoding Agent:** Enriches activities with precise latitude/longitude coordinates (robustly handled to prevent API timeouts).

   -  **Activity Scheduling Agent:** Organizes activities into a logical `DailyPlan`.

5. **Evaluator Agent:** The quality control gate. Performs a strategic value-based analysis of the drafted plan against user constraints.

6. **Efficient Self-Correction Loop:** Based on the Evaluator, the graph either approves the plan or triggers a targeted refinement loop (routing back to **Flight** or **Hotel** agents) to optimize the budget.

7. **Map Generator Node:** Generates an interactive folium map HTML snippet.

8. **Report Formatter:** Creates the final `.md` and `.html` files. Note: These files are saved to a Docker Volume, making them accessible on the host machine immediately.

9. **FastAPI Endpoint:** Streams the final status and JSON response back to the Frontend Container.


```mermaid
graph TD
    subgraph "Host Machine (User Environment)"
        Browser[User's Browser / React UI]
        LocalDisk[("/server/output Folder")]
    end

    subgraph "Docker Infrastructure (Microservices)"
        
        subgraph "Frontend Container"
            Nginx[Nginx Web Server]
            ReactApp[React App Assets]
        end

        subgraph "Backend Container"
            API(FastAPI Endpoint)
            
            subgraph "LangGraph Agentic Core"
                Planner(Planner Agent)
                Flight{Flight Agent}
                Hotel{Hotel Agent}
                Event(Event Agent)
                Agg(Data Aggregator)
                
                Extraction(Activity Extraction)
                Geo(Geocoding Agent)
                Schedule(Activity Scheduling)
                
                Evaluator{Evaluator Agent}
                Map(Map Generator)
                Report(Report Formatter)
            end
            
            Volume[(Shared Docker Volume)]
        end
    end

    %% Flow Connections
    Browser -- "HTTP Request (Port 3000)" --> Nginx
    Nginx -- "Serves App" --> Browser
    Browser -- "API Request (Port 5001)" --> API
    
    API --> Planner
    Planner --> Flight & Hotel & Event
    Flight & Hotel & Event --> Agg
    Agg --> Extraction --> Geo --> Schedule --> Evaluator
    
    Evaluator -->|Refine Hotel| Hotel
    Evaluator -->|Refine Flight| Flight
    Evaluator -->|Approved| Map
    
    Map --> Report
    Report -- "Saves .md & .html" --> Volume
    Volume -.->|Syncs to| LocalDisk
    
    Report --> API
    API -- "JSON Stream" --> Browser
    
 ```

---

## Tech Stack

Category | Tool/Library | Purpose |
:---| :--- | :--- |
| `Infrastructure` | **Docker & Docker Compose** | Containerization and orchestration of microservices. |
| |  **Nginx** | Serving the React frontend production build. |
`AI& Orchestration`  | **Groq(Llama 3)** | High-speed inference engine for agent reasoning. |
| | **LangChain** | Core framework for LLM interactions and tool definitions. |
| | **LangGraph** |  Orchestrates the stateful, multi-agent graph with cycles and parallel execution. |
| | **Pydantic** | Ensures data is structured and reliable throughout the entire workflow. |
`Backend` | **FastAPI** | A high-performance Python framework for building the API server. |
| | **Uvicorn** | The ASGI server that runs the FastAPI application.  |
| | **Python 3.10+** | The core programming language for the backend and agent logic. |
| | **Folium & Geopy** | Map generation and geocoding. |
`Frontend` | **React & Vite** |Building the interactive user interface. |
| | **Axios** | Making HTTP requests from the client to the backend API. |
| | **React-Markdown** | Rendering the final Markdown report beautifully in the UI.|
| `Data Source` | **RapidAPI** | Platform for accessing live Flight and Hotel APIs.|
| | **Tavily** | Live web search for finding real-time activity information.
| | **Ticketmaster** | Live API for discovering concerts, sports, and other events. 


---

##  Installation & Setup

Since the project is fully dockerized, you do not need to install Python or Node.js locally. You only need **Docker Desktop.**

##### 1. Clone the Repository

```bash
git clone https://github.com/berkyalkn/AI-travel-agent
cd AI-travel-agent
```

##### 2. Configure Environment Variables

Create a `.env` file in the **server directory** of the project. This file will be injected into the containers at runtime.

```bash
cd server

# Create .env file
touch .env
```

Add your API keys to the `.env` file:

```bash
GROQ_API_KEY=your_groq_key_here
TAVILY_API_KEY=your_tavily_key_here
RAPIDAPI_KEY=your_rapidapi_key_here
TICKETMASTER_API_KEY=your_ticketmaster_key_here
```

##### 3. Build and Run (Docker Compose)

Run the following command in the root directory. This will build both the Backend and Frontend images and start the services.

```bash
docker-compose up --build
```

Wait until you see `Uvicorn running on http://0.0.0.0:8000` in the logs.

---

## Usage

**1. Open the Application:** Navigate to http://localhost:3000 in your browser.

**2. Submit a request:**
 - Example: "I want to plan trip to New York from Antalya for me and my two best friends between 25.09.2025 and 28.09.2025 . We are interested in adventure, museums, and food, and our total budget is around 8,000 euros."

**3. View the Results:**
- The system will stream the progress of each agent.
- Once complete, you will see a detailed Markdown itinerary and an Interactive Map.

**4. Access Local Reports:** The generated reports (`trip_itinerary.md` and `trip_itinerary.html`) are automatically synced to your local machine via Docker Volumes. You can find them in:

```bash
./server/output/
```
---

## Key Engineering Concepts

This project serves as a showcase of advanced AI Engineering and Cloud Architecture principles:

#### AI & Agentic Patterns

- **Stateful Multi-Agent Orchestration:** Uses LangGraph to manage a complex, cyclic workflow where specialized agents (Planner, Researcher, Evaluator) collaborate through a persistent state (TripState), mimicking a human team structure.

- **Structured Output & Validation:** Enforces strict Pydantic schemas on all LLM outputs. This prevents hallucinations in data structures and ensures the frontend receives reliable, parseable JSON for rendering.

- **Intelligent Self-Correction (Reflection):** Implements a feedback loop inspired by Constitutional AI. The Evaluator Agent critiques the plan against constraints (budget, location). If rejected, it dynamically routes the workflow back to specific agents for targeted refinement, rather than restarting the whole process.

- **Tool Use & Live Grounding:** Demonstrates advanced tool binding where LLMs autonomously query real-time APIs (Booking.com, Ticketmaster, Tavily) to ground their reasoning in current, real-world data.


#### Cloud & System Architecture

- **Microservices Pattern:** Decouples the application into distinct Frontend (React/Nginx) and Backend (FastAPI) containers, communicating via a bridge network. This ensures independent scaling and separation of concerns.

- **Containerization & Security:** Fully dockerized environment following OpenShift security standards (non-root users, arbitrary UID support).

- **Resilient Error Handling:** Implements robust retry mechanisms (exponential backoff) and timeout handling for external APIs (e.g., Geocoding), ensuring system stability even during network latency or API outages.

- **Parallel Execution:** Optimizes performance by executing independent blocking I/O operations (Flight, Hotel, and Event searches) concurrently.

### What You Get

Upon successful execution, the system generates comprehensive outputs accessible via both the Web UI and the local file system:

- **Interactive Web Dashboard:** A real-time UI that streams the agent's thought process and renders the final plan.

- **Smart Budget Breakdown:** A comparative analysis of the estimated cost vs. user budget, including per-person calculations.

- **Rich Markdown Report (trip_itinerary.md):** A detailed, readable document containing flight tables, hotel ratings, and day-by-day schedules.

- **Interactive Map (trip_itinerary.html):** A generated HTML file with an embedded Leaflet/Folium map, plotting every activity with numbered markers for spatial visualization.